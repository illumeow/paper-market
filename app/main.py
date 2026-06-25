import os
import asyncio
import time
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
    repo.seed(conn, cfg, now=time.time())
    app.state.config = cfg
    app.state.conn = conn
    app.state.repo = repo
    app.state.broadcaster = Broadcaster()
    app.state.rate_limiter = RateLimiter(max_per_min=5)
    app.include_router(member_router)
    app.include_router(teller_router)
    app.include_router(public_router)
    if os.path.isdir("frontend"):
        app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
    return app


app = create_app()
