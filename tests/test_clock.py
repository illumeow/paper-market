import pytest
import app.core.db as db
import app.core.clock as clock_mod
from app.core.clock import (set_event_start, elapsed_min, accrued_minutes,
                            pause_event, resume_event, is_paused)


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


# ---------------------------------------------------------------------------
# Pause / resume — the clock freezes while stopped, paused gap never accrues
# ---------------------------------------------------------------------------

def test_pause_freezes_elapsed_and_accrued():
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    pause_event(conn, start + 600)  # stop at 10 min
    assert is_paused(conn)
    # clock frozen at the pause instant no matter how late `now` is
    assert elapsed_min(conn, now=start + 6000) == 10.0
    assert accrued_minutes(conn, since_ts=start, now=start + 6000) == 10.0


def test_pause_is_idempotent():
    conn = _fresh_conn()
    set_event_start(conn, 1_000_000.0)
    pause_event(conn, 1_000_600.0)
    pause_event(conn, 1_000_900.0)  # second call must not move the pause instant
    assert clock_mod.event_paused_at(conn) == 1_000_600.0


def test_resume_excludes_paused_gap():
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at,debt) "
                 "VALUES('0-1','h',1000,?,0)", (start,))
    conn.commit()
    pause_event(conn, start + 600)          # pause at 10 active-min
    resume_event(conn, start + 600 + 300)   # paused 300 s (5 min), then resume
    assert not is_paused(conn)
    now = start + 600 + 300 + 300           # 5 more wall-min after resume
    anchor = conn.execute("SELECT balance_accrued_at FROM members WHERE member_id='0-1'").fetchone()[0]
    # 10 min before pause + 5 after resume = 15; the 5 paused min are excluded
    assert accrued_minutes(conn, since_ts=anchor, now=now) == 15.0
    assert elapsed_min(conn, now=now) == 15.0


def test_resume_shifts_price_history_ts():
    """price_history.ts must slide forward with event_start on resume, else the
    dashboard derives (ts - event_start) wrong and pre-pause points jump left."""
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    conn.execute("INSERT INTO price_history(stock_id,ts,price) VALUES('TECH',?,100)", (start + 300,))
    conn.commit()
    pause_event(conn, start + 600)          # pause at 10 min
    resume_event(conn, start + 600 + 180)   # paused 180 s
    ts = conn.execute("SELECT ts FROM price_history WHERE stock_id='TECH'").fetchone()[0]
    assert ts == start + 300 + 180          # x = (ts - event_start) preserved across the gap


def test_resume_without_pause_is_noop():
    conn = _fresh_conn()
    set_event_start(conn, 1_000_000.0)
    resume_event(conn, 1_000_600.0)  # not paused → no shift
    assert elapsed_min(conn, now=1_000_600.0) == 10.0


def test_accrue_during_pause_does_not_lose_interest_on_resume():
    """A read (lazy accrue) during the pause must not plant a gap timestamp that
    resume_event slides past the resume point — else post-resume interest is lost."""
    from app.bank import service as bank_service
    from app.bank.interest import demand_balance
    conn = _fresh_conn()
    start = 1_000_000.0
    set_event_start(conn, start)
    conn.execute("INSERT INTO members(member_id,pin,balance,balance_accrued_at,debt) "
                 "VALUES('0-1','h',1000,?,0)", (start,))
    conn.commit()
    pause_event(conn, start + 600)                       # pause at 10 active-min
    bank_service.accrue_balance(conn, "0-1", start + 600 + 150)  # mid-pause read
    resume_event(conn, start + 600 + 300)                # resume after 5-min pause
    final = bank_service.accrue_balance(conn, "0-1", start + 600 + 300 + 300)  # +5 active-min
    # 10 min before pause + 5 after resume = 15; the paused 5 min must not count
    # (re-feeding rounded floats through compound drifts in the last digits → approx)
    assert final == pytest.approx(float(demand_balance(1000, 15)), rel=1e-9)
