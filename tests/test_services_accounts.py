import pytest
import app.core.db as db
from app.core.config import load_config
from app.bank import repo as bank_repo
from app.bank import service as bank_service
from app.core.money import compound


def _setup():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at) VALUES('0-1','h',1000,0.0)")
    from app.core.clock import set_event_start; set_event_start(conn, 0.0)  # interest accrues from kickoff
    conn.commit()
    return conn, cfg


def test_accrual_then_deposit():
    conn, _ = _setup()
    bank_service.accrue_balance(conn, "0-1", now=600.0)   # 10 min -> 1000*1.005^10≈1051.14
    bank_service.deposit(conn, "0-1", 100, now=600.0, actor="teller")
    bal = bank_repo.get_member(conn, "0-1")["balance"]
    # balance is now full-precision float: compound(1000, 0.005, 10) + 100 (no rounding)
    assert bal == pytest.approx(float(compound(1000, 0.005, 10)) + 100, rel=1e-9)


def test_withdraw_blocks_negative():
    conn, _ = _setup()
    with pytest.raises(ValueError):
        bank_service.withdraw(conn, "0-1", 5000, now=0.0, actor="teller")


def test_accrual_frozen_before_start_and_anchored_to_kickoff():
    conn = db.connect(":memory:"); db.init_schema(conn)
    load_config()
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at) VALUES('0-1','h',1000,0.0)")
    conn.commit()
    from app.core.clock import set_event_start
    # before kickoff: no interest even though wall-clock advanced 10 min
    assert bank_service.accrue_balance(conn, "0-1", now=600.0) == 1000
    # kickoff at t=600s; at t=1200s only 10 min of *event* time elapsed (not 20)
    set_event_start(conn, 600.0)
    # 10 event-minutes of interest: compound(1000, 0.005, 10), no rounding
    assert bank_service.accrue_balance(conn, "0-1", now=1200.0) == pytest.approx(float(compound(1000, 0.005, 10)), rel=1e-9)


def test_relief_once_only():
    conn, cfg = _setup()
    bank_service.claim_relief(conn, "0-1", now=0.0, actor="teller", relief_amount=500)
    assert bank_repo.get_member(conn, "0-1")["balance"] == 1500
    with pytest.raises(ValueError):
        bank_service.claim_relief(conn, "0-1", now=0.0, actor="teller", relief_amount=500)
