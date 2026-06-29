"""Tests that the debt field returned by /api/me and teller _member_snapshot
reflects live accrued loan interest, not just the raw stored principal."""
import csv
import time
import pytest
from starlette.testclient import TestClient

import app.core.db as _db
from app.bank import repo as bank_repo
from app.bank import service as bank_service
from app.bank.interest import loan_owed
from app.core.clock import set_event_start, accrued_minutes


# ---------------------------------------------------------------------------
# Helpers shared by service-level tests
# ---------------------------------------------------------------------------

def _conn_with_loan(bal=2000, principal=500, loan_at=100.0, event_start_epoch=0.0):
    """In-memory DB with one member who has a loan; event already started."""
    conn = _db.connect(":memory:")
    _db.init_schema(conn)
    conn.execute(
        "INSERT INTO members(member_id,pin,balance,balance_accrued_at,debt,loan_taken_at) "
        "VALUES('0-1','h',?,?,?,?)",
        (bal, loan_at, principal, loan_at),
    )
    conn.commit()
    set_event_start(conn, event_start_epoch)
    return conn


# ---------------------------------------------------------------------------
# Service-level: loan_owed_now
# ---------------------------------------------------------------------------

def test_loan_owed_now_reflects_accrued_interest():
    """loan_owed_now returns live compounded amount > stored debt after elapsed time."""
    principal = 500
    loan_at = 100.0
    event_start_epoch = 0.0
    conn = _conn_with_loan(
        bal=2000, principal=principal, loan_at=loan_at, event_start_epoch=event_start_epoch
    )

    m = bank_repo.get_member(conn, "0-1")

    # Advance 60 event-minutes (TIME_SCALE=1 → 3600 real seconds past event_start)
    now = event_start_epoch + 60 * 60

    owed = bank_service.loan_owed_now(conn, "0-1", now)

    # Must exceed the raw stored principal
    assert owed > principal, f"Expected owed > {principal}, got {owed}"

    # Must exactly match what loan_repay would charge
    elapsed = accrued_minutes(conn, m["loan_taken_at"], now)
    expected = float(loan_owed(principal, elapsed))
    assert abs(owed - expected) < 1e-9, f"Expected {expected}, got {owed}"


def test_loan_owed_now_zero_when_no_loan():
    """loan_owed_now returns 0.0 when the member carries no debt."""
    conn = _db.connect(":memory:")
    _db.init_schema(conn)
    conn.execute(
        "INSERT INTO members(member_id,pin,balance,balance_accrued_at,debt,loan_taken_at) "
        "VALUES('0-1','h',1000,0.0,0,NULL)"
    )
    conn.commit()
    set_event_start(conn, 0.0)
    assert bank_service.loan_owed_now(conn, "0-1", 3600.0) == 0.0


# ---------------------------------------------------------------------------
# Route-level: /api/me debt field
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    from app.core.config import load_config
    from app.core import provision
    c = _db.connect(db_path)
    _db.init_schema(c)
    provision.provision(c, load_config(), pins_path="config/pins.csv")
    c.close()
    from app.main import create_app
    return TestClient(create_app())


def test_me_debt_field_reflects_accrued_interest(client):
    """/api/me debt is live (compounded), not the raw stored principal."""
    conn = client.app.state.conn

    # Login as first member from pins.csv
    row = next(csv.DictReader(open("config/pins.csv")))
    mid = row["member_id"]
    assert (
        client.post("/api/login/member", json={"member_id": mid, "pin": row["pin"]}).status_code
        == 200
    )

    principal = 500
    # Place event_start far enough in the past that ≥1 event-minute has elapsed
    event_start_epoch = time.time() - 3600  # 3600 real seconds = 60 event-minutes at TIME_SCALE=1
    set_event_start(conn, event_start_epoch)

    # Disburse the loan at the moment the event started
    bank_service.loan_disburse(conn, mid, principal, event_start_epoch, "teller", 1000)

    # /api/me is served at the current real time (~60 event-minutes after kickoff)
    r = client.get("/api/me")
    assert r.status_code == 200
    debt = r.json()["debt"]
    assert debt > principal, f"Expected live owed > {principal}, got {debt}"


def test_teller_snapshot_debt_reflects_accrued_interest(client):
    """Teller member snapshot debt is live, matching what a repay would charge."""
    conn = client.app.state.conn
    mid = "0-2"
    principal = 300

    event_start_epoch = time.time() - 3600
    set_event_start(conn, event_start_epoch)
    bank_service.loan_disburse(conn, mid, principal, event_start_epoch, "teller", 1000)

    assert client.post("/api/login/staff", json={"password": "staffpw"}).status_code == 200
    r = client.post("/api/teller/lookup", json={"pin": "8191"})
    assert r.status_code == 200
    debt = r.json()["debt"]
    assert debt > principal, f"Expected live owed > {principal}, got {debt}"
