import os
import time

# Test-only fast-forward multiplier. Default 1.0 = real-time (production behavior
# is byte-identical when TIME_SCALE is unset). Set TIME_SCALE=10 at launch to run
# event-time 10× faster, e.g.:  TIME_SCALE=10 uvicorn app.main:app ...
# Read once at import so the value is stable for the lifetime of the process.
_TIME_SCALE = float(os.environ.get("TIME_SCALE", "1") or "1")
if _TIME_SCALE <= 0:
    _TIME_SCALE = 1.0


def event_start(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='event_start_at'").fetchone()
    return float(row["value"]) if row else None


def set_event_start(conn, epoch):
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('event_start_at',?)", (str(epoch),))
    conn.commit()


def elapsed_min(conn, now=None):
    now = now if now is not None else time.time()
    start = event_start(conn)
    return 0.0 if start is None else (now - start) / 60.0 * _TIME_SCALE


def accrued_minutes(conn, since_ts, now=None):
    """Minutes of *event time* elapsed since ``since_ts``.

    All time-based growth (demand interest, loan interest, FD term) is lazy and
    anchored to the event clock: it counts only from kickoff onward, never from
    provision/server-start. Returns 0.0 before the event starts, and clamps the
    baseline to ``event_start`` so any wall-clock time before kickoff is ignored.
    """
    now = now if now is not None else time.time()
    start = event_start(conn)
    if start is None or since_ts is None:
        return 0.0
    return max(0.0, (now - max(since_ts, start)) / 60.0 * _TIME_SCALE)


def quarter_index(conn, quarter_min, now=None):
    return int(elapsed_min(conn, now) // quarter_min)
