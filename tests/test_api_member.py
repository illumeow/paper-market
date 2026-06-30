import os, time, pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    # provision the temp DB (boot no longer seeds)
    import app.core.db as _db
    from app.core.config import load_config
    from app.core import provision
    c = _db.connect(db_path); _db.init_schema(c)
    provision.provision(c, load_config(), pins_path="config/pins.csv")
    c.close()
    from app.main import create_app
    return TestClient(create_app())


def _login_member(client, pin):  # member_id + pin from config/pins.csv first row
    import csv
    row = next(csv.DictReader(open("config/pins.csv")))
    r = client.post("/api/login/member", json={"member_id": row["member_id"], "pin": row["pin"]})
    assert r.status_code == 200
    return r.json()["member_id"]


def test_member_login_and_me(client):
    mid = _login_member(client, None)
    r = client.get("/api/me")
    assert r.status_code == 200 and r.json()["member_id"] == mid
    assert r.json()["balance"] == 1000  # near t0


def test_bad_pin_rejected(client):
    # valid member_id with wrong pin
    assert client.post("/api/login/member", json={"member_id": "0-1", "pin": "9999"}).status_code in (401, 429)
    # unknown member_id is also rejected
    assert client.post("/api/login/member", json={"member_id": "9-99", "pin": "1234"}).status_code in (401, 429)


def test_member_cannot_access_teller(client):
    _login_member(client, None)
    assert client.post("/api/teller/lookup", json={"pin": "1159"}).status_code == 403


def test_trade_blocked_before_start_then_allowed(client):
    from app.core.clock import set_event_start
    _login_member(client, None)
    assert client.get("/api/dashboard").json()["started"] is False
    r = client.post("/api/trade", json={"stock_id": "TECH", "side": "buy", "shares": 1})
    assert r.status_code == 409
    set_event_start(client.app.state.conn, time.time())
    r2 = client.post("/api/trade", json={"stock_id": "TECH", "side": "buy", "shares": 1})
    assert r2.status_code == 200
    assert "price" in r2.json() and "shares" in r2.json()


def test_me_reports_loan_cap(client):
    _login_member(client, None)
    assert client.get("/api/me").json()["loan_cap"] == 5000  # config/config.toml


def test_member_self_loan_then_settle(client):
    from app.core.clock import set_event_start
    _login_member(client, None)
    set_event_start(client.app.state.conn, time.time())
    # borrow: balance up by the loan, debt equals it (+ negligible t0 interest)
    assert client.post("/api/loan", json={"amount": 2000}).status_code == 200
    me = client.get("/api/me").json()
    assert 2000 <= me["debt"] < 2001 and me["balance"] >= 3000  # 1000 start + 2000
    # partial repay reduces debt and balance
    assert client.post("/api/repay", json={"amount": 500}).status_code == 200
    me = client.get("/api/me").json()
    assert 1500 <= me["debt"] < 1501  # ~2000 owed − 500 paid, interest negligible
    # settle clears the loan in full
    assert client.post("/api/settle").status_code == 200
    assert client.get("/api/me").json()["debt"] == 0


def test_member_loan_blocked_before_kickoff(client):
    _login_member(client, None)
    r = client.post("/api/loan", json={"amount": 1000})
    assert r.status_code == 409 and r.json()["detail"] == "Event not started"


def test_member_loan_over_cap_rejected(client):
    from app.core.clock import set_event_start
    _login_member(client, None)
    set_event_start(client.app.state.conn, time.time())
    r = client.post("/api/loan", json={"amount": 99999})
    assert r.status_code == 400 and r.json()["detail"] == "Invalid loan amount"
