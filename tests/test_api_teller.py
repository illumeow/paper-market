import time
import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("STAFF_PASSWORD", "staffpw")
    monkeypatch.setenv("SECRET_KEY", "k")
    # provision the temp DB (boot no longer seeds)
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


def test_staff_deposit_then_export(client):
    _staff(client)
    client.post("/api/teller/start")  # banking is gated until kickoff
    assert client.get("/api/member/0-1").json()["locked"] is False
    client.post("/api/teller/deposit", json={"id": "0-1", "amount": 250})
    r = client.get("/api/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.split("\n")[0] == ",".join(["member", "amount"] * 10)


def test_cooldown_locks_second_lookup(client):
    _staff(client)
    client.post("/api/teller/start")  # cooldown applies only while the event is live
    client.get("/api/member/0-2")
    second = client.get("/api/member/0-2").json()
    assert second["locked"] is True and second["cooldown_remaining_sec"] > 0


def test_lookup_cooldown_disabled_before_kickoff(client):
    # Pre-kickoff: repeated lookups never lock and don't record a visit, so the
    # live cooldown starts fresh at kickoff.
    _staff(client)
    assert client.get("/api/member/0-2").json()["locked"] is False
    assert client.get("/api/member/0-2").json()["locked"] is False   # still open, no cooldown
    client.post("/api/teller/start")
    assert client.get("/api/member/0-2").json()["locked"] is False   # first live visit, fresh
    assert client.get("/api/member/0-2").json()["locked"] is True    # second within window → locked


def test_lookup_cooldown_disabled_while_paused(client):
    # Paused mirrors pre-kickoff: lookups don't trip the cooldown.
    _staff(client)
    client.post("/api/teller/start")
    client.post("/api/teller/stop")
    assert client.get("/api/member/0-2").json()["locked"] is False
    assert client.get("/api/member/0-2").json()["locked"] is False


def test_session_probe_requires_staff(client):
    assert client.get("/api/teller/session").status_code == 403
    _staff(client)
    assert client.get("/api/teller/session").json()["staff"] is True


def test_logout_clears_session(client):
    _staff(client)
    assert client.get("/api/teller/session").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/teller/session").status_code == 403  # cookie cleared


def test_op_returns_snapshot_without_relocking(client):
    _staff(client)
    client.post("/api/teller/start")  # banking is gated until kickoff
    assert client.get("/api/member/0-1").json()["locked"] is False  # starts the visit
    # The op returns a fresh, unlocked snapshot — no re-lookup needed, so the
    # cooldown started by the lookup never blocks the post-op refresh.
    dep = client.post("/api/teller/deposit", json={"id": "0-1", "amount": 250}).json()
    assert dep["member"]["locked"] is False and dep["member"]["balance"] >= 250
    wd = client.post("/api/teller/withdraw", json={"id": "0-1", "amount": 50}).json()
    assert wd["member"]["locked"] is False


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


def test_stop_then_resume_event(client):
    _staff(client)
    client.post("/api/teller/start")
    s = client.post("/api/teller/stop").json()
    assert s["started"] is True and s["paused"] is True
    assert client.get("/api/dashboard").json()["paused"] is True
    r = client.post("/api/teller/start").json()  # Start doubles as resume
    assert r["paused"] is False
    assert client.get("/api/dashboard").json()["paused"] is False


def test_stop_requires_staff(client):
    assert client.post("/api/teller/stop").status_code == 403


def test_trade_blocked_when_paused(client):
    _staff(client)
    client.post("/api/teller/start")
    client.post("/api/teller/stop")
    r = client.post("/api/teller/trade", json={"id": "0-1", "stock_id": "TECH", "side": "buy", "shares": 1})
    assert r.status_code == 409 and r.json()["detail"] == "event paused"


def test_banking_ops_blocked_when_paused(client):
    _staff(client)
    client.post("/api/teller/start")
    client.post("/api/teller/stop")
    # every state mutation freezes; reads/export stay open
    assert client.post("/api/teller/deposit", json={"id": "0-1", "amount": 100}).status_code == 409
    assert client.post("/api/teller/withdraw", json={"id": "0-1", "amount": 100}).status_code == 409
    assert client.post("/api/teller/fd/open", json={"id": "0-1", "principal": 100, "term": 30}).status_code == 409
    assert client.post("/api/teller/news", json={"text": "x"}).status_code == 409   # news is a write → frozen
    assert client.get("/api/member/0-1").status_code == 200          # read still works
    assert client.get("/api/export").status_code == 200              # export still works
    # resume re-opens banking
    client.post("/api/teller/start")
    assert client.post("/api/teller/deposit", json={"id": "0-1", "amount": 100}).status_code == 200
    assert client.post("/api/teller/news", json={"text": "x"}).status_code == 200


def test_banking_blocked_before_kickoff(client):
    # pre-kickoff mirrors paused: every state mutation is frozen until Start.
    _staff(client)
    r = client.post("/api/teller/deposit", json={"id": "0-1", "amount": 100})
    assert r.status_code == 409 and r.json()["detail"] == "event not started"
    assert client.post("/api/teller/news", json={"text": "x"}).status_code == 409  # news frozen too
    client.post("/api/teller/start")
    assert client.post("/api/teller/deposit", json={"id": "0-1", "amount": 100}).status_code == 200


def test_business_error_returns_400_with_message(client):
    # A domain rejection surfaces as 400 + detail (frontend toasts it), not a 500.
    _staff(client)
    client.post("/api/teller/start")  # past the pre-kickoff gate so business logic runs
    r = client.post("/api/teller/withdraw", json={"id": "0-1", "amount": 999999})
    assert r.status_code == 400
    assert r.json()["detail"] == "insufficient balance"


def test_teller_trade_blocked_before_start(client):
    from app.core.clock import set_event_start
    _staff(client)
    r = client.post("/api/teller/trade", json={"id": "0-1", "stock_id": "TECH", "side": "buy", "shares": 1})
    assert r.status_code == 409
    set_event_start(client.app.state.conn, time.time())
    r2 = client.post("/api/teller/trade", json={"id": "0-1", "stock_id": "TECH", "side": "buy", "shares": 1})
    assert r2.status_code == 200


def test_root_redirects_to_dashboard(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/dashboard"


def test_dashboard_exposes_event_start(client):
    # Before start: event_start key present with null value
    dash = client.get("/api/dashboard").json()
    assert "event_start" in dash
    assert dash["event_start"] is None

    # Staff login and start the event
    _staff(client)
    r = client.post("/api/teller/start")
    assert r.status_code == 200
    since = r.json()["since"]

    # After start: event_start is a number close to `since`
    dash = client.get("/api/dashboard").json()
    assert dash["event_start"] is not None
    assert isinstance(dash["event_start"], float)
    assert abs(dash["event_start"] - since) < 1.0


def test_member_snapshot_is_cooldown_free_read(client):
    # The teller-page refresh path: a read that reflects live state, never locks,
    # is repeatable, and does not consume a cooldown visit.
    _staff(client)
    client.post("/api/teller/start")  # so banking ops past the require_running gate
    # repeatable, never locked
    s1 = client.get("/api/teller/member/0-1/snapshot")
    assert s1.status_code == 200 and s1.json()["locked"] is False
    s2 = client.get("/api/teller/member/0-1/snapshot")
    assert s2.status_code == 200 and s2.json()["locked"] is False
    # reflects a mutation done via a teller op
    client.post("/api/teller/deposit", json={"id": "0-1", "amount": 250})
    assert client.get("/api/teller/member/0-1/snapshot").json()["balance"] >= 250
    # peeking must NOT start a visit: a real lookup afterwards is still unlocked
    assert client.get("/api/member/0-1").json()["locked"] is False
    # unknown member -> 404
    assert client.get("/api/teller/member/9-99/snapshot").status_code == 404


def test_member_snapshot_requires_staff(client):
    assert client.get("/api/teller/member/0-1/snapshot").status_code == 403


def test_stop_broadcasts_status_paused(client):
    # Verify that POST /api/teller/stop publishes a "status" SSE event with paused=True.
    # Strategy: directly inject a Queue into bc._subs before the POST (avoids the async
    # subscribe call), then drain it with get_nowait() after the request returns.
    import asyncio
    _staff(client)
    client.post("/api/teller/start")
    bc = client.app.state.broadcaster
    q = asyncio.Queue()
    bc._subs.add(q)
    try:
        r = client.post("/api/teller/stop")
        assert r.status_code == 200
        # Response shape: must report started=True, paused=True
        body = r.json()
        assert body["started"] is True
        assert body["paused"] is True
        # SSE broadcast: drain queue, find status event with paused=True
        events = []
        while True:
            try:
                events.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break
        status_events = [e for e in events if e["type"] == "status"]
        assert len(status_events) >= 1, "expected at least one 'status' event to be broadcast"
        assert status_events[0]["data"]["paused"] is True
    finally:
        bc._subs.discard(q)


def test_clean_urls_serve_html_and_block_dot_html(client):
    # Extensionless page serves the .html content; direct .html is 404 (one canonical URL).
    ok = client.get("/member")
    assert ok.status_code == 200 and "text/html" in ok.headers["content-type"]
    assert client.get("/member.html").status_code == 404
    assert client.get("/dashboard").status_code == 200
    assert client.get("/teller").status_code == 200
    assert client.get("/css/tokens.css").status_code == 200
