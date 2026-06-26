def get_stock(conn, sid):
    return conn.execute("SELECT * FROM stocks WHERE stock_id=?", (sid,)).fetchone()


def all_stocks(conn):
    return conn.execute("SELECT * FROM stocks").fetchall()


def update_stock(conn, sid, **fields):
    sets = ",".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE stocks SET {sets} WHERE stock_id=?", (*fields.values(), sid))
    conn.commit()


def get_holding(conn, mid, sid):
    r = conn.execute("SELECT shares FROM holdings WHERE member_id=? AND stock_id=?", (mid, sid)).fetchone()
    return r["shares"] if r else 0


def set_holding(conn, mid, sid, shares):
    conn.execute("INSERT INTO holdings(member_id,stock_id,shares) VALUES(?,?,?) "
                 "ON CONFLICT(member_id,stock_id) DO UPDATE SET shares=excluded.shares",
                 (mid, sid, shares))
    conn.commit()


def list_holdings(conn, mid):
    return conn.execute("SELECT stock_id,shares FROM holdings WHERE member_id=? AND shares>0", (mid,)).fetchall()


def add_trade(conn, mid, sid, side, shares, price, ts, actor):
    conn.execute("INSERT INTO trades(member_id,stock_id,side,shares,price,ts,actor) "
                 "VALUES(?,?,?,?,?,?,?)", (mid, sid, side, shares, price, ts, actor))
    conn.commit()


def add_news(conn, text, source, ts):
    conn.execute("INSERT INTO news(text,source,ts) VALUES(?,?,?)", (text, source, ts))
    conn.commit()


def current_news(conn, limit=10):
    return conn.execute("SELECT text,ts,source FROM news ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def latest_news_id(conn):
    return conn.execute("SELECT COALESCE(MAX(id), 0) m FROM news").fetchone()["m"]


def news_after(conn, after_id):
    return conn.execute("SELECT id,text,ts,source FROM news WHERE id>? ORDER BY id ASC",
                        (after_id,)).fetchall()


def due_events(conn, elapsed):
    return conn.execute("SELECT * FROM events WHERE fired=0 AND at_min<=?", (elapsed,)).fetchall()


def active_events(conn, elapsed):
    return conn.execute("SELECT * FROM events WHERE at_min<=? AND ?< at_min+duration_min",
                        (elapsed, elapsed)).fetchall()


def mark_event_fired(conn, id_):
    conn.execute("UPDATE events SET fired=1 WHERE id=?", (id_,))
    conn.commit()
