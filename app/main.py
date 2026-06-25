import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import load_config
from app import db, repo
from app.realtime import Broadcaster
from app.auth import RateLimiter
from app.ticker import run_ticker
from app.api_member import router as member_router
from app.api_teller import router as teller_router
from app.api_public import router as public_router


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        n = app.state.conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"]
        if n == 0:
            raise RuntimeError(
                f"paper-market DB at {app.state.db_path!r} is not provisioned "
                f"(0 members). Run: python scripts/setup_db.py  (add --reset to wipe)."
            )
        app.state.ticker = asyncio.create_task(run_ticker(app))
        try:
            yield
        finally:
            app.state.ticker.cancel()

    app = FastAPI(title="paper-market", lifespan=lifespan)
    cfg = load_config()
    db_path = os.environ.get("DB_PATH", "data/paper.db")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = db.connect(db_path)
    db.init_schema(conn)
    app.state.config = cfg
    app.state.conn = conn
    app.state.db_path = db_path
    app.state.repo = repo
    app.state.broadcaster = Broadcaster()
    app.state.rate_limiter = RateLimiter(max_per_min=5)
    # ticker broadcasts news rows newer than this cursor (so pre-existing rows aren't re-blasted)
    app.state.last_news_id = repo.latest_news_id(conn)
    app.include_router(member_router)
    app.include_router(teller_router)
    app.include_router(public_router)
    if os.path.isdir("frontend"):
        app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
    return app


app = create_app()
