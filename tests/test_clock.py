import app.core.db as db
import app.core.clock as clock_mod
from app.core.clock import set_event_start, elapsed_min, accrued_minutes


def _fresh_conn():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# Default scale (1.0) — real-time behavior
# ---------------------------------------------------------------------------

def test_elapsed_min_default_scale():
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    now = start + 600  # 10 minutes of wall-clock
    assert elapsed_min(conn, now=now) == 10.0


def test_elapsed_min_before_kickoff_returns_zero():
    conn = _fresh_conn()
    assert elapsed_min(conn, now=9999.0) == 0.0


def test_accrued_minutes_default_scale():
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    now = start + 600  # 600 s = 10 min
    assert accrued_minutes(conn, since_ts=start, now=now) == 10.0


def test_accrued_minutes_clamps_pre_kickoff_time():
    """Wall-clock time before kickoff must not count."""
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    since_before_start = start - 300  # 5 min before kickoff
    now = start + 600               # 10 min after kickoff
    # Only the 10 post-kickoff minutes should accrue
    assert accrued_minutes(conn, since_ts=since_before_start, now=now) == 10.0


def test_accrued_minutes_no_event_start_returns_zero():
    conn = _fresh_conn()
    assert accrued_minutes(conn, since_ts=0.0, now=9999.0) == 0.0


# ---------------------------------------------------------------------------
# Scale 10 — fast-forward mode (set via monkeypatch on the module constant)
# ---------------------------------------------------------------------------

def test_elapsed_min_with_scale_10(monkeypatch):
    monkeypatch.setattr("app.core.clock._TIME_SCALE", 10.0)
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    now = start + 600  # 600 s wall-clock → 10 real-min → 100 scaled-min
    assert elapsed_min(conn, now=now) == 100.0


def test_accrued_minutes_with_scale_10(monkeypatch):
    monkeypatch.setattr("app.core.clock._TIME_SCALE", 10.0)
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    now = start + 600
    assert accrued_minutes(conn, since_ts=start, now=now) == 100.0
