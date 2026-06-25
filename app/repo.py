import csv
import hashlib
import time
from app.clock import set_event_start, event_start


def _h(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def seed(conn, config, pins_path="config/pins.csv", now=None):
    now = now if now is not None else time.time()
    if conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 0:
        with open(pins_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                conn.execute(
                    "INSERT INTO members(member_id,pin,balance,balance_accrued_at) VALUES(?,?,?,?)",
                    (row["member_id"], _h(row["pin"]), config.economy["start_balance"], now))
    if conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 0:
        for s in config.stocks:
            conn.execute(
                "INSERT INTO stocks(stock_id,name,price,quarter_open_price,band_floor_pct,"
                "band_ceiling_pct,floor,ceiling,nominal_supply,s0,init_price) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (s["id"], s["name"], float(s["init_price"]), float(s["init_price"]),
                 -0.30, 0.30, float(s["floor"]), float(s["ceiling"]),
                 s["nominal_supply"], s["s0"], float(s["init_price"])))
    if conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 0:
        for e in config.events:
            conn.execute("INSERT INTO events(at_min,stock_id,pct,duration_min,headline) "
                         "VALUES(?,?,?,?,?)",
                         (e["at_min"], e["stock_id"], e["pct"], e["duration_min"], e.get("headline")))
    if event_start(conn) is None:
        set_event_start(conn, now)
    conn.commit()


def get_member(conn, mid):
    return conn.execute("SELECT * FROM members WHERE member_id=?", (mid,)).fetchone()


def get_member_by_pinhash(conn, h):
    return conn.execute("SELECT * FROM members WHERE pin=?", (h,)).fetchone()


def update_member(conn, mid, **fields):
    sets = ",".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE members SET {sets} WHERE member_id=?", (*fields.values(), mid))
    conn.commit()


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


def add_txn(conn, mid, type_, amount, ts, actor):
    conn.execute("INSERT INTO transactions(member_id,type,amount,ts,actor) VALUES(?,?,?,?,?)",
                 (mid, type_, amount, ts, actor))
    conn.commit()


def open_fds(conn, mid):
    return conn.execute("SELECT * FROM fixed_deposits WHERE member_id=? AND closed=0", (mid,)).fetchall()


def get_fd(conn, fd_id):
    return conn.execute("SELECT * FROM fixed_deposits WHERE fd_id=?", (fd_id,)).fetchone()


def add_fd(conn, fd_id, mid, principal, term, rate, created_at):
    conn.execute("INSERT INTO fixed_deposits(fd_id,member_id,principal,term_minutes,rate_per_min,created_at) "
                 "VALUES(?,?,?,?,?,?)", (fd_id, mid, principal, term, rate, created_at))
    conn.commit()


def close_fd(conn, fd_id, matured):
    conn.execute("UPDATE fixed_deposits SET closed=1, matured=? WHERE fd_id=?", (1 if matured else 0, fd_id))
    conn.commit()


def add_news(conn, text, source, ts):
    conn.execute("INSERT INTO news(text,source,ts) VALUES(?,?,?)", (text, source, ts))
    conn.commit()


def current_news(conn, limit=10):
    return conn.execute("SELECT text,ts,source FROM news ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def due_events(conn, elapsed):
    return conn.execute("SELECT * FROM events WHERE fired=0 AND at_min<=?", (elapsed,)).fetchall()


def active_events(conn, elapsed):
    return conn.execute("SELECT * FROM events WHERE at_min<=? AND ?< at_min+duration_min",
                        (elapsed, elapsed)).fetchall()


def mark_event_fired(conn, id_):
    conn.execute("UPDATE events SET fired=1 WHERE id=?", (id_,))
    conn.commit()
