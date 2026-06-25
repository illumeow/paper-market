import pytest, app.db as db
from app.config import load_config
from app import repo, services


def _setup():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at) VALUES('0-1','h',1000,0.0)")
    conn.commit()
    return conn, cfg


def test_accrual_then_deposit():
    conn, _ = _setup()
    services.accrue_balance(conn, "0-1", now=600.0)   # 10 min -> 1000*1.005^10≈1051
    services.deposit(conn, "0-1", 100, now=600.0, actor="teller")
    bal = repo.get_member(conn, "0-1")["balance"]
    assert bal == 1151


def test_withdraw_blocks_negative():
    conn, _ = _setup()
    with pytest.raises(ValueError):
        services.withdraw(conn, "0-1", 5000, now=0.0, actor="teller")


def test_relief_once_only():
    conn, cfg = _setup()
    services.claim_relief(conn, "0-1", now=0.0, actor="teller", relief_amount=500)
    assert repo.get_member(conn, "0-1")["balance"] == 1500
    with pytest.raises(ValueError):
        services.claim_relief(conn, "0-1", now=0.0, actor="teller", relief_amount=500)
