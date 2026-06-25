import pytest
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


def _staff(client):
    assert client.post("/api/login/staff", json={"password": "staffpw"}).status_code == 200


def test_staff_deposit_then_export(client):
    _staff(client)
    assert client.get("/api/member/0-1").json()["locked"] is False
    client.post("/api/teller/deposit", json={"id": "0-1", "amount": 250})
    r = client.get("/api/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.split("\n")[0] == ",".join(["member", "amount"] * 10)


def test_cooldown_locks_second_lookup(client):
    _staff(client)
    client.get("/api/member/0-2")
    second = client.get("/api/member/0-2").json()
    assert second["locked"] is True and second["cooldown_remaining_sec"] > 0


def test_wrong_staff_password(client):
    assert client.post("/api/login/staff", json={"password": "nope"}).status_code == 403


def test_start_sets_clock_and_is_idempotent(client):
    # Before start: dashboard shows not started
    dash = client.get("/api/dashboard").json()
    assert dash["started"] is False
    assert dash["elapsed_min"] == 0 or dash["elapsed_min"] == 0.0

    # Staff login and call start
    _staff(client)
    r = client.post("/api/teller/start")
    assert r.status_code == 200
    assert r.json()["started"] is True
    since = r.json()["since"]
    assert since is not None

    # Dashboard now shows started
    dash = client.get("/api/dashboard").json()
    assert dash["started"] is True

    # Call start again: since must not change (idempotent)
    r2 = client.post("/api/teller/start")
    since2 = r2.json()["since"]
    assert since2 == since


def test_start_requires_staff(client):
    # No auth: 403
    assert client.post("/api/teller/start").status_code == 403
