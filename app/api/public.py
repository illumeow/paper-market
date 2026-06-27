from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.stock import repo as stock_repo
from app.core.auth import COOKIE
from app.core.clock import event_start, elapsed_min, is_paused, _TIME_SCALE

router = APIRouter()


@router.post("/api/logout")
async def logout():
    # One cookie carries both roles, so this logs out member or staff alike.
    # Open by design — clearing your own session needs no auth.
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/", samesite="lax")
    return resp


@router.get("/api/dashboard")
async def dashboard(request: Request):
    conn = request.app.state.conn
    stocks = []
    for s in stock_repo.all_stocks(conn):
        hist = conn.execute("SELECT ts,price FROM price_history WHERE stock_id=? ORDER BY ts",
                            (s["stock_id"],)).fetchall()
        vol = conn.execute("SELECT COALESCE(SUM(shares),0) v FROM trades WHERE stock_id=?",
                          (s["stock_id"],)).fetchone()["v"]
        pct = (s["price"] / s["init_price"] - 1) * 100 if s["init_price"] else 0
        stocks.append({"stock_id": s["stock_id"], "name": s["name"], "price": s["price"],
                       "init_price": s["init_price"],
                       "pct_change": round(pct, 2), "volume": vol,
                       "history": [{"ts": h["ts"], "price": h["price"]} for h in hist]})
    news = [dict(n) for n in stock_repo.current_news(conn, limit=10)]
    return {"stocks": stocks, "news": news,
            "started": event_start(conn) is not None,
            "paused": is_paused(conn),
            "elapsed_min": elapsed_min(conn),
            "event_start": event_start(conn),
            "time_scale": _TIME_SCALE}
