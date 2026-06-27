import os
import time

# Test-only fast-forward multiplier. Default 1.0 = real-time (production behavior
# is byte-identical when TIME_SCALE is unset). Set TIME_SCALE=10 at launch to run
# event-time 10× faster, e.g.:  TIME_SCALE=10 uvicorn app.main:app ...
# Read once at import so the value is stable for the lifetime of the process.
_TIME_SCALE = float(os.environ.get("TIME_SCALE", "1") or "1")
if _TIME_SCALE <= 0:
    _TIME_SCALE = 1.0


def time_scale():
    """The event-time multiplier (1.0 in production). Lets non-event clocks —
    e.g. the teller-visit cooldown — compress under TIME_SCALE for fast testing."""
    return _TIME_SCALE


def event_start(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='event_start_at'").fetchone()
    return float(row["value"]) if row else None


def set_event_start(conn, epoch):
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('event_start_at',?)", (str(epoch),))
    conn.commit()


def event_paused_at(conn):
    """Wall epoch the event was paused (stopped) at, or None if running."""
    row = conn.execute("SELECT value FROM meta WHERE key='event_paused_at'").fetchone()
    return float(row["value"]) if row else None


def is_paused(conn):
    return event_paused_at(conn) is not None


def pause_event(conn, now):
    """Freeze the event clock at ``now``. No-op before kickoff and once already
    paused. Enforcing "only pause a started event" here (not just in the caller)
    guarantees paused ⇒ started, so resume_event's ``start + d`` is never None."""
    if event_start(conn) is None or event_paused_at(conn) is not None:
        return
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('event_paused_at',?)", (str(now),))
    conn.commit()


def resume_event(conn, now):
    """Resume from pause by sliding every clock anchor forward over the paused
    gap, so paused wall-time never counts toward elapsed/interest/FD term. The
    gap ``d`` is added to event_start and to each per-row accrual timestamp, so
    every ``now - since_ts`` delta excludes the pause. No-op if not paused."""
    p = event_paused_at(conn)
    start = event_start(conn)
    if p is None or start is None:   # paused ⇒ started, so start is never None here; explicit for clarity
        return
    d = max(0.0, now - p)
    conn.execute("UPDATE meta SET value=? WHERE key='event_start_at'", (str(start + d),))
    conn.execute("UPDATE members SET balance_accrued_at = balance_accrued_at + ?", (d,))
    conn.execute("UPDATE members SET loan_taken_at = loan_taken_at + ? WHERE loan_taken_at IS NOT NULL", (d,))
    conn.execute("UPDATE members SET last_teller_visit_at = last_teller_visit_at + ? WHERE last_teller_visit_at IS NOT NULL", (d,))
    conn.execute("UPDATE fixed_deposits SET created_at = created_at + ? WHERE closed=0", (d,))
    # Slide history timestamps too: the dashboard derives a point's x from
    # (ts - event_start), so moving event_start forward by d without moving ts
    # would shift every pre-pause point left by d on the next page reload. All
    # rows predate the pause (the ticker is frozen while stopped), so +d keeps
    # their x put and the chart stays continuous across the gap.
    conn.execute("UPDATE price_history SET ts = ts + ?", (d,))
    conn.execute("DELETE FROM meta WHERE key='event_paused_at'")
    conn.commit()


def effective_now(conn, now):
    """Wall ``now`` clamped to the pause instant while paused — this is what
    freezes every lazy accrual the moment the event is stopped. Accrual anchors
    must be stamped with this (not raw ``now``) so a read during the pause does
    not write a gap timestamp that resume_event would then mis-shift."""
    p = event_paused_at(conn)
    return p if p is not None else now


def elapsed_min(conn, now=None):
    now = now if now is not None else time.time()
    start = event_start(conn)
    return 0.0 if start is None else max(0.0, (effective_now(conn, now) - start)) / 60.0 * _TIME_SCALE


def accrued_minutes(conn, since_ts, now=None):
    """Minutes of *event time* elapsed since ``since_ts``.

    All time-based growth (demand interest, loan interest, FD term) is lazy and
    anchored to the event clock: it counts only from kickoff onward, never from
    provision/server-start. Returns 0.0 before the event starts, clamps the
    baseline to ``event_start`` so wall-clock time before kickoff is ignored, and
    freezes at the pause instant while the event is stopped.
    """
    now = now if now is not None else time.time()
    start = event_start(conn)
    if start is None or since_ts is None:
        return 0.0
    return max(0.0, (effective_now(conn, now) - max(since_ts, start)) / 60.0 * _TIME_SCALE)


def quarter_index(conn, quarter_min, now=None):
    return int(elapsed_min(conn, now) // quarter_min)
