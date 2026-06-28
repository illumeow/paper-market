import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    from app.core import db as _db
    from app.core.config import load_config
    from app.core import provision
    c = _db.connect(db_path); _db.init_schema(c)
    provision.provision(c, load_config(), pins_path="config/pins.csv")
    c.close()
    from app.main import create_app
    return TestClient(create_app())


def _staff(client):
    assert client.post("/api/login/staff", json={"password": "staffpw"}).status_code == 200


def _member(client, mid):
    from app.core.auth import make_token, COOKIE
    client.cookies.set(COOKIE, make_token("k", "member", mid))


def _start(client):
    # FD ops are gated until kickoff; anchor the clock at now so elapsed ~0 and
    # the term/remaining assertions below still hold.
    import time
    from app.core.clock import set_event_start
    set_event_start(client.app.state.conn, time.time())


def test_me_exposes_options_and_enriched_fd(client):
    _member(client, "0-1")
    _start(client)
    me = client.get("/api/me").json()
    assert [o["term"] for o in me["fd_options"]] == [30, 60]
    assert me["fixed_deposits"] == []
    assert "elapsed_min" in me and "event_duration_min" in me

    assert client.post("/api/fd/open", json={"principal": 1000, "term": 30}).status_code == 200
    fd = client.get("/api/me").json()["fixed_deposits"]
    assert len(fd) == 1
    fd = fd[0]
    assert fd["payout"] > 1000          # maturity payout surfaced
    assert fd["remaining_min"] == pytest.approx(30.0)
    assert fd["matured"] is False
    assert "fd_id" not in fd            # bound to member, id not exposed


def test_member_limited_to_one_fd(client):
    _member(client, "0-2")
    _start(client)
    assert client.post("/api/fd/open", json={"principal": 500, "term": 30}).status_code == 200
    r = client.post("/api/fd/open", json={"principal": 200, "term": 60})
    assert r.status_code == 400
    assert "already has an open" in r.json()["detail"]


def test_member_can_close_own_fd(client):
    _member(client, "0-4")
    _start(client)
    assert client.post("/api/fd/open", json={"principal": 500, "term": 30}).status_code == 200
    assert client.post("/api/fd/close").status_code == 200
    assert client.get("/api/me").json()["fixed_deposits"] == []
    assert client.post("/api/fd/close").status_code == 400  # nothing left to close


def test_teller_close_by_member_no_fd_id(client):
    _staff(client)
    client.post("/api/teller/start")  # FD ops gated until kickoff
    assert client.post("/api/teller/fd/open",
                       json={"id": "0-3", "principal": 1000, "term": 30}).status_code == 200
    assert client.post("/api/teller/fd/close", json={"id": "0-3"}).status_code == 200  # no fd_id
    r = client.post("/api/teller/fd/close", json={"id": "0-3"})
    assert r.status_code == 400 and r.json()["detail"] == "no open fixed deposit"
