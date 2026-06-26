import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import load_config
from app.core.errors import BusinessError
from app.core import db
from app.stock import repo as stock_repo
from app.core.realtime import Broadcaster
from app.core.auth import RateLimiter
from app.stock.ticker import run_ticker
from app.api.member import router as member_router
from app.api.teller import router as teller_router
from app.api.public import router as public_router


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

    @app.exception_handler(BusinessError)
    async def _business_error(request: Request, exc: BusinessError):
        # Expected user-facing rejection → 400 with the message (frontends toast .detail).
        # A bare ValueError or anything else stays an unhandled 500 (a true server fault).
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    cfg = load_config()
    db_path = os.environ.get("DB_PATH", "data/paper.db")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = db.connect(db_path)
    db.init_schema(conn)
    app.state.config = cfg
    app.state.conn = conn
    app.state.db_path = db_path
    app.state.broadcaster = Broadcaster()
    app.state.rate_limiter = RateLimiter(max_per_min=5)
    # ticker broadcasts news rows newer than this cursor (so pre-existing rows aren't re-blasted)
    app.state.last_news_id = stock_repo.latest_news_id(conn)
    app.include_router(member_router)
    app.include_router(teller_router)
    app.include_router(public_router)
    if os.path.isdir("frontend"):
        @app.get("/")
        async def _root():
            return RedirectResponse("/dashboard.html")
        app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
    return app


app = create_app()
