import time
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from app.bank import repo as bank_repo
from app.bank import service as bank_service
from app.stock import repo as stock_repo
from app.stock import service as stock_service
from app.core.auth import make_token, require_staff, COOKIE
from app.core.clock import event_start, set_event_start, elapsed_min, accrued_minutes
from app.core.cooldown import visit_status
from app.core.networth import member_amount
from app.core.export_csv import build_csv
from app.core.locks import MUTATION_LOCK

router = APIRouter()


@router.post("/api/login/staff")
async def login_staff(request: Request):
    body = await request.json()
    if str(body.get("password", "")) != request.app.state.config.staff_password:
        raise HTTPException(403, "wrong password")
    tok = make_token(request.app.state.config.secret_key, "staff")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, tok, httponly=True, samesite="lax")
    return resp


@router.post("/api/teller/start")
async def t_start(request: Request, _: bool = Depends(require_staff)):
    conn = request.app.state.conn
    async with MUTATION_LOCK:
        if event_start(conn) is None:        # idempotent: only set once, never reset mid-event
            set_event_start(conn, time.time())
        since = event_start(conn)
    return {"started": True, "since": since, "elapsed_min": elapsed_min(conn)}


@router.get("/api/member/{mid}")
async def lookup(request: Request, mid: str, _: bool = Depends(require_staff)):
    conn = request.app.state.conn
    m = bank_repo.get_member(conn, mid)
    if not m:
        raise HTTPException(404, "no such member")
    now = time.time()
    locked, remaining = visit_status(m["last_teller_visit_at"], now,
                                     request.app.state.config.economy["cooldown_min"])
    if locked:
        return {"member_id": mid, "locked": True, "cooldown_remaining_sec": int(remaining)}
    eco = request.app.state.config.economy
    async with MUTATION_LOCK:
        bank_repo.update_member(conn, mid, last_teller_visit_at=now)  # start the visit
        bal = bank_service.accrue_balance(conn, mid, now)
    return {"member_id": mid, "locked": False, "balance": bal, "debt": m["debt"],
            "relief_claimed": bool(m["relief_claimed"]),
            "fixed_deposits": [bank_service.fd_public(conn, f, now, demand_rate=eco["demand_rate"])
                               for f in bank_repo.open_fds(conn, mid)],
            "fd_options": bank_service.fd_term_options(eco),
            "elapsed_min": elapsed_min(conn, now),
            "event_duration_min": eco["event_duration_min"],
            "holdings": [dict(h) for h in stock_repo.list_holdings(conn, mid)]}


def _eco(request):
    return request.app.state.config.economy


@router.post("/api/teller/deposit")
async def t_deposit(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    async with MUTATION_LOCK:
        bank_service.deposit(request.app.state.conn, b["id"], int(b["amount"]), time.time(), "teller")
    return {"ok": True}


@router.post("/api/teller/withdraw")
async def t_withdraw(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    async with MUTATION_LOCK:
        bank_service.withdraw(request.app.state.conn, b["id"], int(b["amount"]), time.time(), "teller")
    return {"ok": True}


@router.post("/api/teller/loan")
async def t_loan(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    async with MUTATION_LOCK:
        bank_service.loan_disburse(request.app.state.conn, b["id"], int(b["amount"]), time.time(),
                                   "teller", _eco(request)["loan_cap"])
    return {"ok": True}


@router.post("/api/teller/repay")
async def t_repay(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    async with MUTATION_LOCK:
        bank_service.loan_repay(request.app.state.conn, b["id"], int(b["amount"]), time.time(), "teller")
    return {"ok": True}


@router.post("/api/teller/relief")
async def t_relief(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    async with MUTATION_LOCK:
        bank_service.claim_relief(request.app.state.conn, b["id"], time.time(), "teller",
                                  _eco(request)["relief_amount"])
    return {"ok": True}


@router.post("/api/teller/fd/open")
async def t_fd_open(request: Request, _: bool = Depends(require_staff)):
    b = await request.json(); eco = _eco(request)
    async with MUTATION_LOCK:
        fd = bank_service.fd_open(request.app.state.conn, b["id"], int(b["principal"]), int(b["term"]),
                                  time.time(), "teller", demand_rate=eco["demand_rate"],
                                  fd_rate_30=eco["fd_rate_30"], fd_rate_60=eco["fd_rate_60"],
                                  event_duration_min=eco["event_duration_min"])
    return {"fd_id": fd}


@router.post("/api/teller/fd/close")
async def t_fd_close(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    async with MUTATION_LOCK:
        bank_service.fd_close_current(request.app.state.conn, b["id"], time.time(), "teller",
                                      demand_rate=_eco(request)["demand_rate"])
    return {"ok": True}


@router.post("/api/teller/trade")
async def t_trade(request: Request, _: bool = Depends(require_staff)):
    if event_start(request.app.state.conn) is None:
        raise HTTPException(409, "event not started")
    b = await request.json(); cfg = request.app.state.config
    async with MUTATION_LOCK:
        res = stock_service.execute_trade(request.app.state.conn, b["id"], b["stock_id"], b["side"],
                                          int(b["shares"]), time.time(), "teller",
                                          tuning=cfg.tuning, noise_scale=cfg.tuning.noise_scale)
    await request.app.state.broadcaster.publish({"type": "prices",
        "data": [{"stock_id": b["stock_id"], "price": res["price"]}]})
    return res


@router.post("/api/teller/news")
async def t_news(request: Request, _: bool = Depends(require_staff)):
    b = await request.json()
    # insert only; the ticker broadcasts it once via the last_news_id cursor (<=tick_seconds later)
    stock_repo.add_news(request.app.state.conn, b["text"], "manual", time.time())
    return {"ok": True}


@router.get("/api/export")
async def export(request: Request, _: bool = Depends(require_staff)):
    conn = request.app.state.conn
    now = time.time()
    prices = {s["stock_id"]: s["price"] for s in stock_repo.all_stocks(conn)}
    amounts = {}
    for g in range(10):
        for i in range(1, 13):
            mid = f"{g}-{i}"
            m = bank_repo.get_member(conn, mid)
            bal = bank_service.accrue_balance(conn, mid, now)
            fds = [{"principal": f["principal"], "term_minutes": f["term_minutes"],
                    "rate_per_min": f["rate_per_min"]} for f in bank_repo.open_fds(conn, mid)]
            holds = [{"stock_id": h["stock_id"], "shares": h["shares"]} for h in stock_repo.list_holdings(conn, mid)]
            le = accrued_minutes(conn, m["loan_taken_at"], now)
            amounts[mid] = member_amount(balance=bal, open_fds=fds, holdings=holds,
                                         prices=prices, debt=m["debt"], loan_elapsed_min=le)
    csv_text = build_csv(amounts)
    return Response(csv_text, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=paper-market.csv"})
