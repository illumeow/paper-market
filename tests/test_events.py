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
                       quarter_min=30, tick_min=5/60, rng=__import__("random"),
                       band_defaults={s["id"]: (s["band_floor_pct"], s["band_ceiling_pct"]) for s in cfg.stocks})
    assert conn.execute("SELECT COUNT(*) c FROM events WHERE fired=1").fetchone()["c"] >= 1
    assert conn.execute("SELECT COUNT(*) c FROM news WHERE source='event'").fetchone()["c"] >= 1


def test_tick_payload_carries_elapsed():
    # The dashboard plots each live point at the server's tick `elapsed`, not from
    # its own clock — so every broadcast item must carry it.
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config(); provision.seed(conn, cfg, pins_path="config/pins.csv", now=0.0)
    updated = events.tick_prices(conn, now=10*60, tuning=cfg.tuning, noise_scale=0.0,
                                 quarter_min=cfg.quarter_min, tick_min=5/60, rng=__import__("random"),
                                 band_defaults={s["id"]: (s["band_floor_pct"], s["band_ceiling_pct"]) for s in cfg.stocks})
    assert updated and all("elapsed" in u for u in updated)
    assert all(abs(u["elapsed"] - 10.0) < 1e-6 for u in updated)
    assert all("volume" in u for u in updated)


def test_quarter_rollover_resets_band():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config(); provision.seed(conn, cfg, pins_path="config/pins.csv", now=0.0)
    # simulate a band that got ratcheted during quarter 0
    stock_repo.update_stock(conn, "TECH", band_floor_pct=-0.9, band_ceiling_pct=0.9)
    # tick after crossing into quarter 1 (>= 30 min). noise_scale=0 so no noise, no organic ratchet.
    # rollover must reset bands to the per-stock config defaults, not hardcoded ±0.30.
    band_defaults = {s["id"]: (s["band_floor_pct"], s["band_ceiling_pct"]) for s in cfg.stocks}
    band_defaults["TECH"] = (-0.20, 0.25)   # override to a non-default value to prove the reset uses band_defaults
    events.tick_prices(conn, now=31*60, tuning=cfg.tuning, noise_scale=0.0,
                       quarter_min=cfg.quarter_min, tick_min=5/60, rng=__import__("random"),
                       band_defaults=band_defaults)
    s = stock_repo.get_stock(conn, "TECH")
    assert s["band_floor_pct"] == -0.20 and s["band_ceiling_pct"] == 0.25
