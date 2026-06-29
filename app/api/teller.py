import time
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from app.bank import repo as bank_repo
from app.bank import service as bank_service
from app.stock import repo as stock_repo
from app.stock import service as stock_service
from app.core.auth import make_token, require_staff, COOKIE, pin_hash
from app.core.clock import (event_start, set_event_start, elapsed_min, accrued_minutes, time_scale,
                            is_paused, pause_event, resume_event)
from app.api.deps import require_running
from app.core.cooldown import visit_status
from app.core.networth import member_networth
from app.core.export_csv import build_csv
from app.core.locks import MUTATION_LOCK

router = APIRouter()


@router.post("/api/login/staff")
async def login_staff(request: Request):
    body = await request.json()
    if str(body.get("password", "")) != request.app.state.config.staff_password:
        raise HTTPException(403, "Wrong password")
    tok = make_token(request.app.state.config.secret_key, "staff")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, tok, httponly=True, samesite="lax")
    return resp


@router.get("/api/teller/session")
async def t_session(_: bool = Depends(require_staff)):
    # Lightweight probe so the teller page can restore a staff session on reload
    # (the pm_session cookie is httponly — JS can't read it, must ask the server).
    return {"staff": True}


def _member_snapshot(conn, mid, now, eco):
    """The unlocked member view returned by lookup. Teller ops return this so the
    page refreshes from the op's own response — never a re-lookup, which would
    re-hit the cooldown gate and leave the panel stale. Carries the enriched FD
    view (payout/remaining/options) so the FD card stays live after every op."""
    return {"member_id": mid, "locked": False, "balance": bank_service.accrue_balance(conn, mid, now),
            "debt": bank_service.loan_owed_now(conn, mid, now),
            "fixed_deposits": [bank_service.fd_public(conn, f, now, demand_rate=eco["demand_rate"])
                               for f in bank_repo.open_fds(conn, mid)],
            "fd_options": bank_service.fd_term_options(eco),
            "elapsed_min": elapsed_min(conn, now),
            "event_duration_min": eco["event_duration_min"],
            "holdings": [dict(h) for h in stock_repo.list_holdings(conn, mid)]}


@router.post("/api/teller/run")
async def t_run(request: Request, _: bool = Depends(require_staff)):
    # Doubles as kickoff and resume: first call sets the clock (never reset mid-
    # event); a call while paused resumes (slides anchors past the paused gap).
    conn = request.app.state.conn
    now = time.time()
    async with MUTATION_LOCK:
        if event_start(conn) is None:
            set_event_start(conn, now)
        elif is_paused(conn):
            resume_event(conn, now)
        since = event_start(conn)
    await request.app.state.broadcaster.publish({"type": "status",
        "data": {"started": True, "paused": False, "elapsed_min": elapsed_min(conn)}})
    return {"started": True, "paused": False, "since": since, "elapsed_min": elapsed_min(conn)}


@router.post("/api/teller/pause")
async def t_pause(request: Request, _: bool = Depends(require_staff)):
    # Freeze the event: market + trading + all interest/FD accrual stop at `now`.
    # Idempotent; reversible via /run (resume). No-op before kickoff.
    conn = request.app.state.conn
    async with MUTATION_LOCK:
        if event_start(conn) is not None:
            pause_event(conn, time.time())
    started = event_start(conn) is not None
    paused = is_paused(conn)
    em = elapsed_min(conn)
    await request.app.state.broadcaster.publish({"type": "status",
        "data": {"started": started, "paused": paused, "elapsed_min": em}})
    return {"started": started, "paused": paused, "elapsed_min": em}


@router.post("/api/teller/lookup")
async def lookup(request: Request, _: bool = Depends(require_staff)):
    conn = request.app.state.conn
    b = await request.json()
    m = bank_repo.get_member_by_pin(conn, pin_hash(str(b.get("pin", ""))))
    if not m:
        raise HTTPException(404, "No such member")
    mid = m["member_id"]
    now = time.time()
    eco = request.app.state.config.economy
    # The teller-visit cooldown applies only while the event is live. Before
    # kickoff and while paused, staff look members up freely: the lock is not
    # checked and the visit is NOT recorded, so the live cooldown starts fresh
    # at kickoff/resume instead of inheriting a setup-time visit.
    running = event_start(conn) is not None and not is_paused(conn)
    if running:
        locked, remaining = visit_status(m["last_teller_visit_at"], now,
                                         eco["cooldown_min"], time_scale=time_scale())
        if locked:
            return {"member_id": mid, "locked": True, "cooldown_remaining_sec": int(remaining)}
    async with MUTATION_LOCK:
        if running:
            bank_repo.update_member(conn, mid, last_teller_visit_at=now)  # start the visit
        return _member_snapshot(conn, mid, now, eco)


@router.get("/api/teller/member/{mid}/snapshot")
async def member_snapshot(request: Request, mid: str, _: bool = Depends(require_staff)):
    # Cooldown-free read of the member's CURRENT state, used to refresh an on-screen
    # visit after a page reload — WITHOUT starting a new visit or tripping the lookup
    # cooldown. Mutates via lazy accrual (accrue_balance persists), so it takes the
    # lock like lookup does; it deliberately does NOT touch last_teller_visit_at.
    conn = request.app.state.conn
    m = bank_repo.get_member(conn, mid)
    if not m:
        raise HTTPException(404, "No such member")
    now = time.time()
    async with MUTATION_LOCK:
        return _member_snapshot(conn, mid, now, _eco(request))


def _eco(request):
    return request.app.state.config.economy


@router.post("/api/teller/deposit")
async def t_deposit(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        bank_service.deposit(conn, b["id"], int(b["amount"]), now, "teller")
        return {"ok": True, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/withdraw")
async def t_withdraw(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        bank_service.withdraw(conn, b["id"], int(b["amount"]), now, "teller")
        return {"ok": True, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/loan")
async def t_loan(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        bank_service.loan_disburse(conn, b["id"], int(b["amount"]), now, "teller", _eco(request)["loan_cap"])
        return {"ok": True, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/repay")
async def t_repay(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        bank_service.loan_repay(conn, b["id"], int(b["amount"]), now, "teller")
        return {"ok": True, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/settle")
async def t_settle(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        bank_service.loan_settle(conn, b["id"], now, "teller")
        return {"ok": True, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/fd/open")
async def t_fd_open(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); eco = _eco(request); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        fd = bank_service.fd_open(conn, b["id"], int(b["principal"]), int(b["term"]),
                                  now, "teller", demand_rate=eco["demand_rate"],
                                  fd_rate_30=eco["fd_rate_30"], fd_rate_60=eco["fd_rate_60"],
                                  event_duration_min=eco["event_duration_min"])
        return {"fd_id": fd, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/fd/close")
async def t_fd_close(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        bank_service.fd_close_current(conn, b["id"], now, "teller", demand_rate=_eco(request)["demand_rate"])
        return {"ok": True, "member": _member_snapshot(conn, b["id"], now, _eco(request))}


@router.post("/api/teller/trade")
async def t_trade(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json(); cfg = request.app.state.config; conn = request.app.state.conn; now = time.time()
    async with MUTATION_LOCK:
        res = stock_service.execute_trade(conn, b["id"], b["stock_id"], b["side"],
                                          int(b["shares"]), now, "teller",
                                          tuning=cfg.tuning, noise_scale=cfg.tuning.noise_scale)
        snap = _member_snapshot(conn, b["id"], now, _eco(request))
    await request.app.state.broadcaster.publish({"type": "prices",
        "data": [{"stock_id": b["stock_id"], "price": res["price"]}]})
    return {**res, "member": snap}


@router.post("/api/teller/news")
async def t_news(request: Request, _: bool = Depends(require_staff), __: bool = Depends(require_running)):
    b = await request.json()
    # insert only; the ticker broadcasts it once via the last_news_id cursor (<=tick_seconds later)
    async with MUTATION_LOCK:
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
                    "rate_per_min": f["rate_per_min"],
                    "elapsed_min": accrued_minutes(conn, f["created_at"], now)}
                   for f in bank_repo.open_fds(conn, mid)]
            holds = [{"stock_id": h["stock_id"], "shares": h["shares"]} for h in stock_repo.list_holdings(conn, mid)]
            le = accrued_minutes(conn, m["loan_taken_at"], now)
            amounts[mid] = member_networth(balance=bal, open_fds=fds, holdings=holds,
                                           prices=prices, debt=m["debt"], loan_elapsed_min=le)
    csv_text = build_csv(amounts)
    return Response(csv_text, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=paper-market.csv"})
