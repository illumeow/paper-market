import uuid
from app.bank import repo
from app.core.clock import elapsed_min, accrued_minutes, effective_now
from app.core.errors import BusinessError
from app.bank.interest import demand_balance, loan_owed, fd_maturity, fd_early_exit


def accrue_balance(conn, mid, now) -> float:
    m = repo.get_member(conn, mid)
    minutes = accrued_minutes(conn, m["balance_accrued_at"], now)
    new_bal = float(demand_balance(m["balance"], minutes))
    # Stamp the anchor at effective-now: while paused this is the frozen pause
    # instant, so a read during the pause can't plant a gap timestamp that
    # resume_event would slide past the resume point (→ lost interest).
    repo.update_member(conn, mid, balance=new_bal, balance_accrued_at=effective_now(conn, now))
    return new_bal


def deposit(conn, mid, amount, now, actor):
    if amount <= 0:
        raise BusinessError("amount must be positive")
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + amount)
    repo.add_txn(conn, mid, "deposit", amount, now, actor)


def withdraw(conn, mid, amount, now, actor):
    if amount <= 0:
        raise BusinessError("amount must be positive")
    bal = accrue_balance(conn, mid, now)
    if amount > bal:
        raise BusinessError("insufficient balance")
    repo.update_member(conn, mid, balance=bal - amount)
    repo.add_txn(conn, mid, "withdraw", -amount, now, actor)


def loan_disburse(conn, mid, amount, now, actor, loan_cap):
    if amount <= 0 or amount > loan_cap:
        raise BusinessError("invalid loan amount")
    m = repo.get_member(conn, mid)
    if m["debt"] > 0:
        raise BusinessError("existing loan must be repaid first")
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + amount, debt=amount, loan_taken_at=now)
    repo.add_txn(conn, mid, "loan_out", amount, now, actor)


def loan_repay(conn, mid, amount, now, actor):
    if amount <= 0:
        raise BusinessError("amount must be positive")
    m = repo.get_member(conn, mid)
    if m["debt"] <= 0:
        raise BusinessError("no outstanding loan")
    elapsed = accrued_minutes(conn, m["loan_taken_at"], now)
    owed = float(loan_owed(m["debt"], elapsed))
    bal = accrue_balance(conn, mid, now)
    pay = min(amount, owed)
    if pay > bal:
        raise BusinessError("insufficient balance to repay")
    new_debt = owed - pay
    repo.update_member(conn, mid, balance=bal - pay, debt=new_debt,
                       loan_taken_at=(None if new_debt == 0 else now))
    repo.add_txn(conn, mid, "loan_repay", -pay, now, actor)


def loan_owed_now(conn, mid, now) -> float:
    """Live amount owed on a member's loan: stored debt compounded at the loan
    rate over event-time elapsed since loan_taken_at. Read-only (no anchor
    re-stamp). 0.0 when no loan. Self-fetches the member like the other
    (conn, mid, now) service functions. Matches what loan_repay charges and what
    networth.member_amount counts against net worth, so displayed debt equals
    the real owed."""
    m = repo.get_member(conn, mid)
    if m["debt"] <= 0:
        return 0.0
    elapsed = accrued_minutes(conn, m["loan_taken_at"], now)
    return float(loan_owed(m["debt"], elapsed))


def fd_open(conn, mid, principal, term, now, actor, *, demand_rate, fd_rate_30,
            fd_rate_60, event_duration_min):
    if term not in (30, 60):
        raise BusinessError("term must be 30 or 60")
    if principal <= 0:
        raise BusinessError("principal must be positive")
    if repo.open_fds(conn, mid):
        raise BusinessError("member already has an open fixed deposit")
    if elapsed_min(conn, now) + term > event_duration_min:
        raise BusinessError("past opening cutoff")
    bal = accrue_balance(conn, mid, now)
    if principal > bal:
        raise BusinessError("insufficient balance")
    rate = fd_rate_30 if term == 30 else fd_rate_60
    fd_id = uuid.uuid4().hex[:12]
    repo.update_member(conn, mid, balance=bal - principal)
    repo.add_fd(conn, fd_id, mid, principal, term, rate, now)
    repo.add_txn(conn, mid, "fd_open", -principal, now, actor)
    return fd_id


def fd_close(conn, mid, fd_id, now, actor, *, demand_rate):
    fd = repo.get_fd(conn, fd_id)
    if fd is None or fd["closed"] or fd["member_id"] != mid:
        raise BusinessError("invalid fixed deposit")
    elapsed = accrued_minutes(conn, fd["created_at"], now)
    if elapsed >= fd["term_minutes"]:
        payout = float(fd_maturity(fd["principal"], fd["term_minutes"], fd["rate_per_min"]))
        matured = True
    else:
        payout = float(fd_early_exit(fd["principal"], elapsed, demand_rate))
        matured = False
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + payout)
    repo.close_fd(conn, fd_id, matured)
    repo.add_txn(conn, mid, "fd_close", payout, now, actor)


def fd_close_current(conn, mid, now, actor, *, demand_rate):
    """Close the member's single open FD (one-FD-per-member invariant) — no fd_id needed."""
    fds = repo.open_fds(conn, mid)
    if not fds:
        raise BusinessError("no open fixed deposit")
    fd_close(conn, mid, fds[0]["fd_id"], now, actor, demand_rate=demand_rate)


def close_matured_fds(conn, now, *, demand_rate):
    """Sweep: auto-close every open FD that has reached its term, crediting the
    matured payout. Called each ticker tick so maturity settles event-wide,
    independent of whether anyone is viewing, and frees the one-FD slot."""
    closed = 0
    for fd in repo.all_open_fds(conn):
        if accrued_minutes(conn, fd["created_at"], now) >= fd["term_minutes"]:
            fd_close(conn, fd["member_id"], fd["fd_id"], now, "system", demand_rate=demand_rate)
            closed += 1
    return closed


def fd_term_options(eco):
    """The selectable FD terms + their per-minute rates (drives the open-form chooser)."""
    return [{"term": 30, "rate": eco["fd_rate_30"]},
            {"term": 60, "rate": eco["fd_rate_60"]}]


def fd_public(conn, fd, now, *, demand_rate):
    """Client-facing FD view: base fields + derived maturity payout, the amount
    a close-right-now would return (matured payout, else early-exit penalty value),
    remaining event-minutes, and matured flag (server owns the clock + formulas)."""
    elapsed = accrued_minutes(conn, fd["created_at"], now)
    term = fd["term_minutes"]
    matured = elapsed >= term
    payout = float(fd_maturity(fd["principal"], term, fd["rate_per_min"]))
    close_value_now = payout if matured else float(fd_early_exit(fd["principal"], elapsed, demand_rate))
    return {
        "principal": fd["principal"],
        "term_minutes": term,
        "rate_per_min": fd["rate_per_min"],
        "payout": payout,
        "close_value_now": close_value_now,
        "remaining_min": max(0.0, term - elapsed),
        "matured": matured,
    }
