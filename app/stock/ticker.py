import asyncio
import time
from app.core.locks import MUTATION_LOCK
from app.stock import events
from app.stock import repo as stock_repo
from app.bank import service as bank_service
from app.core.clock import event_start, _TIME_SCALE


async def run_ticker(app):
    cfg = app.state.config
    # tick_min stays real (event-minutes per tick); TIME_SCALE compresses real
    # time by ticking faster, so the ticks-per-event-minute — hence event-drift
    # accumulation and noise statistics — match 1× exactly, just faster.
    tick_min = cfg.tick_seconds / 60.0
    tick_sleep = cfg.tick_seconds / _TIME_SCALE
    import random
    while True:
        await asyncio.sleep(tick_sleep)
        now = time.time()
        if event_start(app.state.conn) is None:
            continue   # event not started: market frozen, no price evolution
        async with MUTATION_LOCK:
            updated = events.tick_prices(app.state.conn, now, tuning=cfg.tuning,
                                         noise_scale=cfg.tuning.noise_scale, quarter_min=cfg.quarter_min,
                                         tick_min=tick_min, rng=random)
            # settle any FD that reached its term this tick (auto-close → payout to balance)
            bank_service.close_matured_fds(app.state.conn, now, demand_rate=cfg.economy["demand_rate"])
            # publish each news row exactly once, in order, via a server-global cursor
            fresh = [dict(r) for r in stock_repo.news_after(app.state.conn, app.state.last_news_id)]
            if fresh:
                app.state.last_news_id = fresh[-1]["id"]
        await app.state.broadcaster.publish({"type": "prices", "data": updated})
        for n in fresh:
            await app.state.broadcaster.publish({"type": "news", "data": n})
