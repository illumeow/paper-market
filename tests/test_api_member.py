import os, time, pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    # provision the temp DB (boot no longer seeds)
    import app.db as _db
    from app.config import load_config
    from app import repo
    c = _db.connect(db_path); _db.init_schema(c)
    repo.provision(c, load_config(), pins_path="config/pins.csv")
    c.close()
    from app.main import create_app
    return TestClient(create_app())


def _login_member(client, pin):  # pin from config/pins.csv first row
    import csv
    pin = next(csv.DictReader(open("config/pins.csv")))["pin"]
    r = client.post("/api/login/member", json={"pin": pin})
    assert r.status_code == 200
    return r.json()["member_id"]


def test_member_login_and_me(client):
    mid = _login_member(client, None)
    r = client.get("/api/me")
    assert r.status_code == 200 and r.json()["member_id"] == mid
    assert r.json()["balance"] == 1000  # near t0


def test_bad_pin_rejected(client):
    assert client.post("/api/login/member", json={"pin": "999999"}).status_code in (401, 429)


def test_member_cannot_access_teller(client):
    _login_member(client, None)
    assert client.get("/api/member/0-1").status_code == 403


def test_trade_blocked_before_start_then_allowed(client):
    from app.clock import set_event_start
    _login_member(client, None)
    assert client.get("/api/dashboard").json()["started"] is False
    r = client.post("/api/trade", json={"stock_id": "TECH", "side": "buy", "shares": 1})
    assert r.status_code == 409
    set_event_start(client.app.state.conn, time.time())
    r2 = client.post("/api/trade", json={"stock_id": "TECH", "side": "buy", "shares": 1})
    assert r2.status_code == 200
    assert "price" in r2.json() and "shares" in r2.json()
