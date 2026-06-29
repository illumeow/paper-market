import pytest
import app.core.db as db
from app.bank import repo as bank_repo
from app.bank import service as bank_service


def _m(bal=1000, debt=0, loan_at=None):
    conn = db.connect(":memory:"); db.init_schema(conn)
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at,debt,loan_taken_at) "
                 "VALUES('0-1','h',?,0.0,?,?)", (bal, debt, loan_at))
    conn.commit(); return conn


def test_disburse_sets_debt_and_balance():
    conn = _m()
    bank_service.loan_disburse(conn, "0-1", 5000, now=0.0, actor="teller", loan_cap=5000)
    m = bank_repo.get_member(conn, "0-1")
    assert m["debt"] == 5000 and m["balance"] == 6000 and m["loan_taken_at"] == 0.0


def test_disburse_over_cap_blocked():
    conn = _m()
    with pytest.raises(ValueError):
        bank_service.loan_disburse(conn, "0-1", 6000, now=0.0, actor="teller", loan_cap=5000)


def test_second_loan_blocked_until_repaid():
    conn = _m(debt=100, loan_at=0.0)
    with pytest.raises(ValueError):
        bank_service.loan_disburse(conn, "0-1", 100, now=0.0, actor="teller", loan_cap=5000)


def test_repay_reduces_debt_and_balance():
    conn = _m(bal=10000, debt=1000, loan_at=0.0)
    bank_service.loan_repay(conn, "0-1", 500, now=0.0, actor="teller")  # owed≈1000 at t=0
    m = bank_repo.get_member(conn, "0-1")
    assert m["debt"] == 500 and m["balance"] == 9500


def test_overpay_repays_only_what_is_owed():
    conn = _m(bal=10000, debt=1000, loan_at=0.0)
    bank_service.loan_repay(conn, "0-1", 5000, now=0.0, actor="teller")  # owed≈1000 at t=0, overpay 5000
    m = bank_repo.get_member(conn, "0-1")
    assert m["debt"] == 0
    assert m["balance"] == 9000   # only 1000 charged, not 5000
    assert m["loan_taken_at"] is None


def test_repay_snaps_subcent_residual_to_zero():
    # Paying within half a cent of owed must close the loan, not leave a sub-cent
    # residual that re-anchors and keeps compounding at the loan rate.
    conn = _m(bal=10000, debt=1000, loan_at=0.0)  # owed == 1000 at t=0
    bank_service.loan_repay(conn, "0-1", 999.998, now=0.0, actor="teller")
    m = bank_repo.get_member(conn, "0-1")
    assert m["debt"] == 0
    assert m["loan_taken_at"] is None
    assert m["balance"] == 10000 - 999.998   # only what was paid is charged


def test_repay_keeps_residual_at_or_above_threshold():
    # A genuine partial repayment (>= half a cent left) must NOT be snapped away.
    conn = _m(bal=10000, debt=1000, loan_at=0.0)
    bank_service.loan_repay(conn, "0-1", 999, now=0.0, actor="teller")
    m = bank_repo.get_member(conn, "0-1")
    assert m["debt"] == 1
    assert m["loan_taken_at"] == 0.0   # re-anchored, loan still open


def test_settle_pays_exact_fractional_owed():
    # An integer repay can never fully clear a fractional debt; settle pays the
    # exact full-precision amount owed and closes the loan.
    conn = _m(bal=10000, debt=1000.5, loan_at=0.0)  # owed == 1000.5 at t=0
    bank_service.loan_settle(conn, "0-1", now=0.0, actor="teller")
    m = bank_repo.get_member(conn, "0-1")
    assert m["debt"] == 0
    assert m["loan_taken_at"] is None
    assert m["balance"] == 8999.5   # full 1000.5 charged


def test_settle_blocked_when_balance_too_low():
    conn = _m(bal=500, debt=1000.5, loan_at=0.0)
    with pytest.raises(ValueError):
        bank_service.loan_settle(conn, "0-1", now=0.0, actor="teller")


def test_settle_no_loan_rejected():
    conn = _m(bal=500, debt=0)
    with pytest.raises(ValueError):
        bank_service.loan_settle(conn, "0-1", now=0.0, actor="teller")
