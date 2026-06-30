import csv
import hashlib
import time
from app.core.clock import set_event_start, event_start


def _h(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def provision(conn, config, pins_path="config/pins.csv", now=None):
    """Provision the database with members, stocks, and events (idempotent, no clock)."""
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
                "band_ceiling_pct,floor,ceiling,pressure_normalizer,market_share_baseline,"
                "init_price,total_market_shares) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["id"], s["name"], float(s["init_price"]), float(s["init_price"]),
                 s["band_floor_pct"], s["band_ceiling_pct"], float(s["floor"]), float(s["ceiling"]),
                 s["pressure_normalizer"], s["market_share_baseline"],
                 float(s["init_price"]), 0))
    if conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 0:
        for e in config.events:
            # stock_id/pct/duration_min are optional: an event with only at_min +
            # headline is a banner-only event (no stock impact). Missing fields go in
            # NULL — due_events still fires the headline; event_drift_for skips them.
            conn.execute("INSERT INTO events(at_min,stock_id,pct,duration_min,headline) "
                         "VALUES(?,?,?,?,?)",
                         (e["at_min"], e.get("stock_id"), e.get("pct"),
                          e.get("duration_min"), e.get("headline")))
    conn.commit()


def seed(conn, config, pins_path="config/pins.csv", now=None):
    """Provision the database and set the event clock if not already set."""
    now = now if now is not None else time.time()
    provision(conn, config, pins_path, now)
    if event_start(conn) is None:
        set_event_start(conn, now)
    conn.commit()
