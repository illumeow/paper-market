import time


def event_start(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='event_start_at'").fetchone()
    return float(row["value"]) if row else None


def set_event_start(conn, epoch):
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('event_start_at',?)", (str(epoch),))
    conn.commit()


def elapsed_min(conn, now=None):
    now = now if now is not None else time.time()
    start = event_start(conn)
    return 0.0 if start is None else (now - start) / 60.0


def quarter_index(conn, quarter_min, now=None):
    return int(elapsed_min(conn, now) // quarter_min)
