import asyncio
import time
from app.locks import MUTATION_LOCK
from app import events
from app.clock import event_start


async def run_ticker(app):
    cfg = app.state.config
    tick_min = cfg.tick_seconds / 60.0
    import random
    repo = app.state.repo
    while True:
        await asyncio.sleep(cfg.tick_seconds)
        now = time.time()
        if event_start(app.state.conn) is None:
            continue   # event not started: market frozen, no price evolution
        async with MUTATION_LOCK:
            updated = events.tick_prices(app.state.conn, now, tuning=cfg.tuning,
                                         noise_scale=cfg.tuning.noise_scale, quarter_min=cfg.quarter_min,
                                         tick_min=tick_min, rng=random)
            # publish each news row exactly once, in order, via a server-global cursor
            fresh = [dict(r) for r in repo.news_after(app.state.conn, app.state.last_news_id)]
            if fresh:
                app.state.last_news_id = fresh[-1]["id"]
        await app.state.broadcaster.publish({"type": "prices", "data": updated})
        for n in fresh:
            await app.state.broadcaster.publish({"type": "news", "data": n})
