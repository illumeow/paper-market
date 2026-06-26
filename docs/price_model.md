# Price Model

How a stock's price evolves each tick. Code lives in `app/domain/price_engine.py`
(`next_price`, pure function) and `app/events.py` (`tick_prices` / `event_drift_for`,
the per-tick driver). Knobs live in `config/config.toml` (`[tuning]` global,
`[[stocks]]` per stock). All money is integer units; prices are floats internally,
rounded on display.

## The per-tick equation

For each stock, every `tick_seconds`:

```
net_flow   = net_flow · net_flow_decay + signed_shares          # momentum accumulator

impact          =  beta · signed_shares / depth                 # this trade's instant jolt
momentum        =  mu · net_flow                                # decaying trend
supply_pressure = -gamma · (total_supply_held − s0) / nominal_supply   # mean reversion
noise           =  uniform(−sigma, +sigma)                      # random walk

organic = price · (1 + impact + momentum + supply_pressure + noise)
organic = clamp(organic, quarter_open·(1+band_floor_pct), quarter_open·(1+band_ceiling_pct))   # SOFT band
final   = organic · (1 + event_drift)                           # scripted news — bypasses the soft band
#  …if final pushed past a band edge, ratchet that edge outward by |event_pct|…
final   = clamp(final, floor, ceiling)                          # HARD absolute limits
```

`signed_shares` is `+shares` on a buy, `−shares` on a sell, and **0** for an
untraded ticker step. So a quiet market (no trades, no active event, holdings at
`s0`) reduces to `organic = price · (1 + noise)` — a pure multiplicative random
walk bounded by the soft band.

## Tuning knobs — `[tuning]`, global (all stocks)

| param | default | role | increasing it → |
|---|---|---|---|
| `beta` | 0.5 | trade-impact strength | each share moves price more |
| `depth` | 500 | market depth (impact divisor) | each share moves price **less** (deeper book) |
| `mu` | 0.02 | momentum strength | trends run harder after trades |
| `net_flow_decay` | 0.95 | momentum memory | trend fades slower (0 = instant kill, 1 = never) |
| `gamma` | 0.02 | mean-reversion strength | pulls back toward baseline float harder |
| `sigma` | 0.005 | noise amplitude | bigger random wiggle (±0.5% per tick now) |
| `tick_seconds` | 5 | tick interval | how often the whole step fires |

The knobs pair up by what they control:

- **`beta` + `depth` → instant impact.** Per-share impact is `beta/depth = 0.001`.
  `depth/beta = 1000` shares = a +100% jolt (before clamps). A 10-share buy ≈ +1%.
- **`mu` + `net_flow_decay` → momentum.** After a 10-share buy, `net_flow = 10` and
  `momentum = 0.02·10 = +20%` on the next tick → rails toward the band edge, then
  decays ×0.95/tick (half-life ≈ 14 ticks). The model is punchy by design.
- **`gamma` + `s0` + `nominal_supply` → slow anti-inflation.** Net-buying 1000 shares
  past `s0` gives `supply_pressure = −0.02·1000/10000 = −0.2%/tick` — a gentle,
  persistent pull back to baseline. This is the term that, mis-anchored, caused the
  cold-start drift bug (see below).

## Per-stock constants — `[[stocks]]`

| param | role |
|---|---|
| `init_price` | starting price **and** the initial `quarter_open` (first band anchor) |
| `floor` / `ceiling` | **hard** absolute price clamps (provisioned at 0.3× / 3× `init_price`); never breached, even by events |
| `nominal_supply` | normalizer for `supply_pressure` — the "total float" scale (10000) |
| `s0` | equilibrium-holdings anchor and mean-reversion target (3000); also the cold-start value of `total_supply_held` |

## Per-stock state (evolves in the DB)

| param | role |
|---|---|
| `price` | current price, carried tick → tick |
| `quarter_open` | price at the start of the current 30-min quarter; the soft band is measured off this. Reset on each `quarter_min` rollover |
| `band_floor_pct` / `band_ceiling_pct` | the **soft** band, ±0.30 at quarter start. Organic moves clamp here; events bypass it and **ratchet** these wider |
| `net_flow` | decaying signed-share momentum accumulator |
| `total_supply_held` | cumulative net shares (buys − sells), provisioned to `s0`; drives `supply_pressure`. Only a price-model anchor — real holdings live in the `holdings` table |

## Per-call inputs (set by the caller, not stored)

| param | source | role |
|---|---|---|
| `signed_shares` | `+shares` buy / `−shares` sell; **0** for the ticker | drives `impact`, feeds `net_flow` |
| `event_drift` | `events.event_drift_for` | compound per-tick news push; compounds to exactly `pct` over the event's `duration_min` |
| `event_pct` | dominant active event `pct` | only sizes the band **ratchet** width |
| `noise` | `rng.uniform(−sigma, sigma)` | the random walk |

### How `event_drift` works

`event_drift_for` (events.py) builds a per-tick rate so multiplying it each tick
compounds to the event's headline `pct`:

```
per_tick = (1 + pct) ** (tick_min / duration_min) − 1
```

Over `duration_min / tick_min` ticks, `(1 + per_tick)^N = (1 + pct)` exactly. That
is why the engine applies it **multiplicatively** as `organic · (1 + event_drift)`
— an additive `organic + price·event_drift` would differ only by the negligible
second-order term `price·noise·per_tick` and would forfeit the clean compounding.
Concurrent events on the same stock sum their `per_tick`; `"all"` targets every
stock.

## Layers of control, by timescale

1. **`impact`** — instant, this trade only.
2. **`momentum`** — fast, decays over ~14 ticks.
3. **`supply_pressure`** — slow, persistent pull toward `s0`.
4. **`noise`** — every tick, mean 0.
5. **soft band** (`quarter_open ± 30%`) — caps organic chaos; resets each quarter.
6. **events** — scripted, escape the soft band and ratchet it outward.
7. **hard `floor` / `ceiling`** — last line of defense, never crossed.

## Cold-start behavior (and a fixed bug)

At kickoff, before anyone trades and before any event fires, the only live term is
`noise`, so price is a pure random walk inside the ±30% band.

This held only after fixing a provisioning bug: `total_supply_held` was defaulting
to `0` while `s0 = 3000`, so `supply_pressure = −0.02·(0 − 3000)/10000 = +0.6%/tick`
— a constant upward push that dominated the ±0.5% noise and rammed the +30% ceiling
within minutes. `provision()` now seeds `total_supply_held = s0`, making
`supply_pressure = 0` at equilibrium. Existing databases must be re-provisioned
(`scripts/setup_db.py --reset --force`) for the fix to take effect.
