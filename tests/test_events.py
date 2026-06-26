import app.core.db as db
from app.core.config import load_config
from app.core import provision
from app.stock import repo as stock_repo
from app.stock import events
from app.stock.engine import Tuning


def test_ramp_drift_compounds_to_pct():
    drift, pct = events.event_drift_for("ENGY",
        [{"stock_id": "ENGY", "pct": 0.10, "duration_min": 5}], tick_min=5/60)
    # over 5 min (60 ticks of 5s) compounding drift ≈ 10%
    total = (1 + drift) ** (5 / (5/60)) - 1
    assert abs(total - 0.10) < 1e-6
    assert pct == 0.10


def test_due_event_fires_and_publishes_news():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config(); provision.seed(conn, cfg, pins_path="config/pins.csv", now=0.0)
    # advance to 40 min (example event at 35)
    events.tick_prices(conn, now=40 * 60, tuning=cfg.tuning, noise_scale=0.0,
                       quarter_min=30, tick_min=5/60, rng=__import__("random"))
    assert conn.execute("SELECT COUNT(*) c FROM events WHERE fired=1").fetchone()["c"] >= 1
    assert conn.execute("SELECT COUNT(*) c FROM news WHERE source='event'").fetchone()["c"] >= 1


def test_quarter_rollover_resets_band():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config(); provision.seed(conn, cfg, pins_path="config/pins.csv", now=0.0)
    # simulate a band that got ratcheted during quarter 0
    stock_repo.update_stock(conn, "TECH", band_floor_pct=-0.9, band_ceiling_pct=0.9)
    # tick after crossing into quarter 1 (>= 30 min). noise_scale=0 so no noise, no organic ratchet.
    events.tick_prices(conn, now=31*60, tuning=cfg.tuning, noise_scale=0.0,
                       quarter_min=cfg.quarter_min, tick_min=5/60, rng=__import__("random"))
    s = stock_repo.get_stock(conn, "TECH")
    assert s["band_floor_pct"] == -0.30 and s["band_ceiling_pct"] == 0.30
