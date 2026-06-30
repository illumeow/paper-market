# Stocks

How a stock's price evolves each tick. Code lives in `app/stock/engine.py`
(`next_price`, pure function) and `app/stock/events.py` (`tick_prices` / `event_drift_for`,
the per-tick driver). Knobs live in `config/config.toml` (`[tuning]` global,
`[[stocks]]` per stock). Prices are carried **full-precision** as floats and never
rounded internally; frontends format to 2dp for display, and rounding half-up to
whole units happens only at the export/scoreboard boundary (`core.money._int`).

## The per-tick equation

For each stock, every `tick_seconds`:

```
flow_momentum   = flow_momentum · momentum_decay + trade_shares          # momentum accumulator

impact          =  impact_strength · trade_shares / impact_depth         # this trade's instant jolt
momentum        =  momentum_strength · flow_momentum                     # decaying trend
supply_pressure = -reversion_strength · (total_market_shares − market_share_baseline) / pressure_normalizer   # mean reversion
noise           =  uniform(−noise_scale, +noise_scale)                   # random walk

organic = price · (1 + impact + momentum + supply_pressure + noise)
organic = clamp(organic, quarter_open·(1+band_floor_pct), quarter_open·(1+band_ceiling_pct))   # SOFT band
final   = organic · (1 + event_drift)                           # scripted news — bypasses the soft band
#  …if final pushed past a band edge, ratchet that edge outward by |event_pct|…
final   = clamp(final, floor, ceiling)                          # HARD absolute limits
```

`trade_shares` is `+shares` on a buy, `−shares` on a sell, and **0** for an
untraded ticker step. So a quiet market (no trades, no active event, holdings at
`market_share_baseline`) reduces to `organic = price · (1 + noise)` — a pure multiplicative random
walk bounded by the soft band.

## Tuning knobs — `[tuning]`, global (all stocks)

| param | default | role | increasing it → |
|---|---|---|---|
| `impact_strength` | 0.5 | trade-impact strength | each share moves price more |
| `impact_depth` | 500 | market depth (impact divisor) | each share moves price **less** (deeper book) |
| `momentum_strength` | 0.002 | momentum strength | trends run harder after trades |
| `momentum_decay` | 0.95 | momentum memory | trend fades slower (0 = instant kill, 1 = never) |
| `reversion_strength` | 0.02 | mean-reversion strength | pulls back toward baseline float harder |
| `noise_scale` | 0.005 | noise amplitude | bigger random wiggle (±0.5% per tick now) |
| `tick_seconds` | 5 | tick interval | how often the whole step fires |

The knobs pair up by what they control:

- **`impact_strength` + `impact_depth` → instant impact.** Per-share impact is `impact_strength/impact_depth = 0.001`.
  `impact_depth/impact_strength = 1000` shares = a +100% jolt (before clamps). A 10-share buy ≈ +1%.
- **`momentum_strength` + `momentum_decay` → momentum.** After a 10-share buy, `flow_momentum = 10` and
  `momentum = 0.002·10 = +2%` on the next tick → rails toward the band edge, then
  decays ×0.95/tick (half-life ≈ 14 ticks). The model is punchy by design.
- **`reversion_strength` + `market_share_baseline` + `pressure_normalizer` → anti-inflation.** With `market_share_baseline = 0`,
  net-buying 1000 shares gives `supply_pressure = −0.02·1000/1000 = −2%/tick` — a persistent pull back
  toward the baseline float. `market_share_baseline` is a tunable *offset*: shifting it and the cold-start
  `total_market_shares` together moves the equilibrium without changing any dynamics (see cold-start below).

## Per-stock constants — `[[stocks]]`

| param | role |
|---|---|
| `init_price` | starting price **and** the initial `quarter_open` (first band anchor) |
| `floor` / `ceiling` | **hard** absolute price clamps (set per stock in config; the committed config uses 0.3× / 3× `init_price`); never breached, even by events |
| `pressure_normalizer` | normalizer for `supply_pressure` — the "total float" scale (1000) |
| `market_share_baseline` | mean-reversion target / equilibrium-holdings anchor (**0**); a tunable offset for `supply_pressure`. Cold-start `total_market_shares` is provisioned to **0** to match, so `supply_pressure = 0` at kickoff |

## Per-stock state (evolves in the DB)

| param | role |
|---|---|
| `price` | current price, carried tick → tick |
| `quarter_open` | price at the start of the current 30-min quarter; the soft band is measured off this. Reset on each `quarter_min` rollover |
| `band_floor_pct` / `band_ceiling_pct` | the **soft** band, seeded per-stock from config (±0.30) and reset to it each quarter start. Organic moves clamp here; events bypass it and **ratchet** these wider |
| `flow_momentum` | decaying signed-share momentum accumulator |
| `total_market_shares` | cumulative net shares (buys − sells), provisioned to **0** (no shares traded yet); drives `supply_pressure`. Only a price-model anchor — real holdings live in the `holdings` table |

## Per-call inputs (set by the caller, not stored)

| param | source | role |
|---|---|---|
| `trade_shares` | `+shares` buy / `−shares` sell; **0** for the ticker | drives `impact`, feeds `flow_momentum` |
| `event_drift` | `events.event_drift_for` | compound per-tick news push; compounds to exactly `pct` over the event's `duration_min` |
| `event_pct` | dominant active event `pct` | only sizes the band **ratchet** width |
| `noise` | `rng.uniform(−noise_scale, noise_scale)` | the random walk |

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
3. **`supply_pressure`** — slow, persistent pull toward `market_share_baseline`.
4. **`noise`** — every tick, mean 0.
5. **soft band** (`quarter_open ± 30%`) — caps organic chaos; resets each quarter.
6. **events** — scripted, escape the soft band and ratchet it outward.
7. **hard `floor` / `ceiling`** — last line of defense, never crossed.

## Cold-start behavior

At kickoff, before anyone trades and before any event fires, the only live term is
`noise`, so price is a pure random walk inside the ±30% band.

This requires `supply_pressure = 0` at equilibrium, which now holds **by construction**:
both `market_share_baseline` and the provisioned `total_market_shares` are **0**, so
`supply_pressure = −0.02·(0 − 0)/1000 = 0`. Because the term depends only on the *deviation*
`total_market_shares − market_share_baseline`, the baseline is a free offset — moving both off
`0` together leaves every price dynamic identical.

Earlier this was mis-anchored: `total_market_shares` defaulted to `0` while
`market_share_baseline = 3000`, giving `supply_pressure = −0.02·(0 − 3000)/1000 = +6%/tick`
— a constant upward push that buried the ±0.5% noise and rammed the +30% ceiling within
minutes. Zeroing the baseline removes the trap entirely. After changing these provisioning
values, existing databases must be re-provisioned (`scripts/setup_db.py --reset --force`).
