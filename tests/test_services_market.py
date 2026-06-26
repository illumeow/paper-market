import app.db as db
from app.config import load_config
from app import repo, services
from app.domain.price_engine import Tuning


def _setup():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config(); repo.seed(conn, cfg, pins_path="config/pins.csv", now=0.0)
    return conn, cfg


def test_buy_deducts_cost_and_adds_shares():
    conn, cfg = _setup()
    p0 = repo.get_stock(conn, "TECH")["price"]
    bal0 = repo.get_member(conn, "0-1")["balance"]
    services.execute_trade(conn, "0-1", "TECH", "buy", 5, now=0.0, actor="member",
                           tuning=cfg.tuning, noise_scale=0.0)
    assert repo.get_holding(conn, "0-1", "TECH") == 5
    assert repo.get_member(conn, "0-1")["balance"] == bal0 - int(round(p0 * 5))
    # total_market_shares is provisioned to market_share_baseline (equilibrium anchor); a buy of 5 adds to it
    baseline = repo.get_stock(conn, "TECH")["market_share_baseline"]
    assert repo.get_stock(conn, "TECH")["total_market_shares"] == baseline + 5


def test_buy_insufficient_cash_blocked():
    conn, cfg = _setup()
    import pytest
    with pytest.raises(ValueError):
        services.execute_trade(conn, "0-1", "TECH", "buy", 100000, now=0.0,
                               actor="member", tuning=cfg.tuning, noise_scale=0.0)


def test_sell_requires_shares():
    conn, cfg = _setup()
    import pytest
    with pytest.raises(ValueError):
        services.execute_trade(conn, "0-1", "TECH", "sell", 1, now=0.0,
                               actor="member", tuning=cfg.tuning, noise_scale=0.0)
