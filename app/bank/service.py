import uuid
from app.bank import repo
from app.core.clock import elapsed_min, accrued_minutes
from app.core.errors import BusinessError
from app.bank.interest import demand_balance, loan_owed, fd_maturity, fd_early_exit
from app.core.money import _int


def accrue_balance(conn, mid, now) -> int:
    m = repo.get_member(conn, mid)
    minutes = accrued_minutes(conn, m["balance_accrued_at"], now)
    new_bal = _int(demand_balance(m["balance"], minutes))
    repo.update_member(conn, mid, balance=new_bal, balance_accrued_at=now)
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


def claim_relief(conn, mid, now, actor, relief_amount):
    m = repo.get_member(conn, mid)
    if m["relief_claimed"]:
        raise BusinessError("relief already claimed")
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + relief_amount, relief_claimed=1)
    repo.add_txn(conn, mid, "relief", relief_amount, now, actor)


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
    owed = _int(loan_owed(m["debt"], elapsed))
    bal = accrue_balance(conn, mid, now)
    pay = min(amount, owed)
    if pay > bal:
        raise BusinessError("insufficient balance to repay")
    new_debt = owed - pay
    repo.update_member(conn, mid, balance=bal - pay, debt=new_debt,
                       loan_taken_at=(None if new_debt == 0 else now))
    repo.add_txn(conn, mid, "loan_repay", -pay, now, actor)


def fd_open(conn, mid, principal, term, now, actor, *, demand_rate, fd_rate_30,
            fd_rate_60, event_duration_min):
    if term not in (30, 60):
        raise BusinessError("term must be 30 or 60")
    if principal <= 0:
        raise BusinessError("principal must be positive")
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
        payout = _int(fd_maturity(fd["principal"], fd["term_minutes"], fd["rate_per_min"]))
        matured = True
    else:
        payout = _int(fd_early_exit(fd["principal"], elapsed, demand_rate))
        matured = False
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + payout)
    repo.close_fd(conn, fd_id, matured)
    repo.add_txn(conn, mid, "fd_close", payout, now, actor)
