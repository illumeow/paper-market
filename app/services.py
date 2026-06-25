from decimal import Decimal, ROUND_HALF_UP
from app import repo
from app.domain.interest import demand_balance, loan_owed


def _int(d) -> int:
    return int(Decimal(d).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def accrue_balance(conn, mid, now) -> int:
    m = repo.get_member(conn, mid)
    minutes = max(0.0, (now - m["balance_accrued_at"]) / 60.0)
    new_bal = _int(demand_balance(m["balance"], minutes))
    repo.update_member(conn, mid, balance=new_bal, balance_accrued_at=now)
    return new_bal


def deposit(conn, mid, amount, now, actor):
    if amount <= 0:
        raise ValueError("amount must be positive")
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + amount)
    repo.add_txn(conn, mid, "deposit", amount, now, actor)


def withdraw(conn, mid, amount, now, actor):
    if amount <= 0:
        raise ValueError("amount must be positive")
    bal = accrue_balance(conn, mid, now)
    if amount > bal:
        raise ValueError("insufficient balance")
    repo.update_member(conn, mid, balance=bal - amount)
    repo.add_txn(conn, mid, "withdraw", -amount, now, actor)


def claim_relief(conn, mid, now, actor, relief_amount):
    m = repo.get_member(conn, mid)
    if m["relief_claimed"]:
        raise ValueError("relief already claimed")
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + relief_amount, relief_claimed=1)
    repo.add_txn(conn, mid, "relief", relief_amount, now, actor)


def loan_disburse(conn, mid, amount, now, actor, loan_cap):
    if amount <= 0 or amount > loan_cap:
        raise ValueError("invalid loan amount")
    m = repo.get_member(conn, mid)
    if m["debt"] > 0:
        raise ValueError("existing loan must be repaid first")
    bal = accrue_balance(conn, mid, now)
    repo.update_member(conn, mid, balance=bal + amount, debt=amount, loan_taken_at=now)
    repo.add_txn(conn, mid, "loan_out", amount, now, actor)


def loan_repay(conn, mid, amount, now, actor):
    if amount <= 0:
        raise ValueError("amount must be positive")
    m = repo.get_member(conn, mid)
    if m["debt"] <= 0:
        raise ValueError("no outstanding loan")
    elapsed = max(0.0, (now - m["loan_taken_at"]) / 60.0)
    owed = _int(loan_owed(m["debt"], elapsed))
    bal = accrue_balance(conn, mid, now)
    if amount > bal:
        raise ValueError("insufficient balance to repay")
    new_debt = max(0, owed - amount)
    repo.update_member(conn, mid, balance=bal - amount, debt=new_debt,
                       loan_taken_at=(None if new_debt == 0 else now))
    repo.add_txn(conn, mid, "loan_repay", -amount, now, actor)
