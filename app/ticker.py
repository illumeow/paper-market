import asyncio
import time
from app.locks import MUTATION_LOCK
from app import events
from app.clock import event_start


async def run_ticker(app):
    cfg = app.state.config
    tick_min = cfg.tick_seconds / 60.0
    import random
    while True:
        await asyncio.sleep(cfg.tick_seconds)
        now = time.time()
        if event_start(app.state.conn) is None:
            continue   # event not started: market frozen, no price evolution
        async with MUTATION_LOCK:
            updated = events.tick_prices(app.state.conn, now, tuning=cfg.tuning,
                                         sigma=cfg.tuning.sigma, quarter_min=cfg.quarter_min,
                                         tick_min=tick_min, rng=random)
            news = [dict(r) for r in app.state.repo.current_news(app.state.conn, limit=1)]
        await app.state.broadcaster.publish({"type": "prices", "data": updated})
        if news:
            await app.state.broadcaster.publish({"type": "news", "data": news[0]})
