from fastapi import Request, HTTPException
from app.core.clock import event_start, is_paused


def require_running(request: Request):
    # The event must be live for any state mutation: not before kickoff and not
    # while paused. Pre-kickoff and paused are now treated identically — every
    # banking/trade write is frozen until Start. Distinct messages so the
    # frontend can tell the two states apart. Reads/lookup/news/start-stop stay open.
    conn = request.app.state.conn
    if event_start(conn) is None:
        raise HTTPException(409, "Event not started")
    if is_paused(conn):
        raise HTTPException(409, "Event paused")
    return True
