# Events

Scripted, timed market happenings: a news banner, a price move, or both. Code
lives in `app/stock/events.py` (`tick_prices` driver, `event_drift_for` math),
`app/stock/repo.py` (the `events` / `news` SQL), and `app/core/provision.py`
(loads rows from config). Schedule lives in `config/config.toml` as `[[events]]`
blocks. Events are read every tick by the ticker (`app/stock/ticker.py`).

## Config schema — `[[events]]`

| field | type | required | role |
|---|---|---|---|
| `at_min` | number | **yes** | when it fires, in **event-minutes from kickoff** (see clock note) |
| `headline` | string | no | news banner text; published once when the event fires |
| `stock_id` | string | no | which stock it drives (`"all"` = every stock) |
| `pct` | number | no | total price change over the window (e.g. `0.10` = +10%) |
| `duration_min` | number | no | how long the price drift is spread across |

`stock_id` / `pct` / `duration_min` move together — they describe a **price
move**. `headline` is independent. Which fields you supply selects the shape:

| `stock_id`/`pct`/`duration` | `headline` | result |
|---|---|---|
| set | set | price drifts **and** banner fires |
| set | omitted | price drifts **silently**, no banner |
| omitted | set | banner only, **no price effect** |
| omitted | omitted | no-op (fires, does nothing) |

Omitted fields are stored as SQL `NULL` (`provision.py` reads them with `.get`).

```toml
# drift + banner
[[events]]
at_min = 5
stock_id = "ENGY"
pct = 0.10
duration_min = 5
headline = "Energy demand spikes — EnergyX surges"

# banner only — no market impact
[[events]]
at_min = 20
headline = "Camp announcement — bonus round at the casino"

# no banner — BANK drifts +12% silently
[[events]]
at_min = 25
stock_id = "BANK"
pct = 0.12
duration_min = 5
```

## Lifecycle

Each `[[events]]` row becomes one row in the `events` table at provision
(`id`, the config fields, plus `fired` defaulting to `0`). Provision is
idempotent and inserts events only when the table is empty.

Every tick, `tick_prices` does two separate things with events, gated by two
different SQL queries (`repo.py`):

1. **Fire the banner** — `due_events(elapsed)` = `fired=0 AND at_min<=elapsed`.
   Each due event is marked `fired=1` (`mark_event_fired`, so it fires **once**),
   and if it has a truthy `headline`, a `news` row is inserted with
   `source='event'`. Firing uses **only** `at_min` + `headline` — it ignores the
   stock fields and `duration_min`.

2. **Apply the price drift** — `active_events(elapsed)` =
   `at_min<=elapsed AND elapsed < at_min+duration_min`. For every stock,
   `event_drift_for` sums the per-tick drift of active events whose `stock_id`
   matches that stock (or `"all"`), and feeds it to `next_price` as `event_drift`.

So the banner is a **one-shot** at `at_min`; the drift is spread across the whole
`[at_min, at_min + duration_min)` **window**. A banner-only event has `NULL`
`duration_min`, so it never appears in `active_events` and never drifts; its
`NULL` `stock_id` also matches no stock in `event_drift_for`. A no-banner event
has a `NULL` `headline`, so step 1 fires it but publishes no news while step 2
still drifts the price.

## How the drift compounds

`event_drift_for` builds a per-tick rate so that multiplying price by it each
tick compounds to exactly the headline `pct` over the event's window:

```
per_tick = (1 + pct) ** (tick_min / duration_min) − 1
```

`next_price` applies it as `final = organic · (1 + event_drift)`, which
**bypasses the soft quarter band** and **ratchets** that band outward if it
pushes past an edge (sized by `event_pct`, the dominant active event's `pct`).
Concurrent events on the same stock sum their `per_tick`. Full price math and
the band/ratchet rules are in [stock.md](stock.md).

## The event clock

`at_min` is **event-time from kickoff**, not wall-clock. `clock.elapsed_min`
returns minutes since `meta.event_start_at`, is `0.0` before kickoff, and freezes
while the event is paused — so events never fire before **Start event** and the
schedule pauses with the market. `TIME_SCALE` compresses event-time (ticker,
clock, and dashboard axis all scale together), so a low `at_min` fires fast under
`TIME_SCALE` for local testing.

## Contracts & gotchas

- A **stock-targeted** event (including `stock_id = "all"`) must carry `pct` and
  `duration_min`. Omitting `pct` while targeting a stock would hit `(1 + None)`
  in the drift math; omitting `duration_min` keeps it out of `active_events` so
  it never drifts. These are config-authoring errors, not supported shapes.
- A **banner-only** event must carry a `headline`, or it is a silent no-op.
- `config.toml`'s committed timings are **placeholder/test values** — set the
  real schedule before the actual event.
- Manual teller news (`POST /api/teller/news`) is a separate path: it only
  *inserts* a `news` row; the ticker broadcasts it via the `last_news_id`
  cursor, same as event headlines.
