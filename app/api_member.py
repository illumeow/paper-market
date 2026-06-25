import time
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from app import repo, services
from app.auth import pin_hash, make_token, require_member, COOKIE
from app.clock import event_start

router = APIRouter()


@router.post("/api/login/member")
async def login_member(request: Request):
    body = await request.json()
    ip = request.client.host if request.client else "?"
    if not request.app.state.rate_limiter.check(ip):
        raise HTTPException(429, "too many attempts")
    conn = request.app.state.conn
    m = repo.get_member_by_pinhash(conn, pin_hash(str(body.get("pin", ""))))
    if not m:
        raise HTTPException(401, "invalid PIN")
    tok = make_token(request.app.state.config.secret_key, "member", m["member_id"])
    resp = JSONResponse({"member_id": m["member_id"]})
    resp.set_cookie(COOKIE, tok, httponly=True, samesite="lax")
    return resp


@router.get("/api/me")
async def me(request: Request, mid: str = Depends(require_member)):
    conn = request.app.state.conn
    now = time.time()
    bal = services.accrue_balance(conn, mid, now)
    m = repo.get_member(conn, mid)
    holdings = [dict(h) for h in repo.list_holdings(conn, mid)]
    fds = [dict(f) for f in repo.open_fds(conn, mid)]
    return {"member_id": mid, "balance": bal, "debt": m["debt"],
            "holdings": holdings, "fixed_deposits": fds}


@router.get("/api/market")
async def market(request: Request):
    return [{"stock_id": s["stock_id"], "name": s["name"], "price": s["price"],
             "init_price": s["init_price"]} for s in repo.all_stocks(request.app.state.conn)]


@router.post("/api/trade")
async def trade(request: Request, mid: str = Depends(require_member)):
    if event_start(request.app.state.conn) is None:
        raise HTTPException(409, "event not started")
    from app.locks import MUTATION_LOCK
    body = await request.json()
    cfg = request.app.state.config
    async with MUTATION_LOCK:
        res = services.execute_trade(request.app.state.conn, mid, body["stock_id"],
                                     body["side"], int(body["shares"]), time.time(), "member",
                                     tuning=cfg.tuning, sigma=cfg.tuning.sigma)
    await request.app.state.broadcaster.publish({"type": "prices", "data": [
        {"stock_id": body["stock_id"], "price": res["price"]}]})
    return res


@router.get("/api/stream")
async def stream(request: Request):
    bc = request.app.state.broadcaster
    q = await bc.subscribe()

    async def gen():
        try:
            while True:
                event = await q.get()
                yield {"event": event["type"], "data": __import__("json").dumps(event["data"])}
        finally:
            bc.unsubscribe(q)

    return EventSourceResponse(gen())
