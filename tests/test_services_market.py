import app.core.db as db
from app.core.config import load_config
from app.core import provision
from app.bank import repo as bank_repo
from app.stock import repo as stock_repo
from app.stock import service as stock_service
from app.stock.engine import Tuning


def _setup():
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config(); provision.seed(conn, cfg, pins_path="config/pins.csv", now=0.0)
    return conn, cfg


def test_buy_deducts_cost_and_adds_shares():
    conn, cfg = _setup()
    p0 = stock_repo.get_stock(conn, "TECH")["price"]
    bal0 = bank_repo.get_member(conn, "0-1")["balance"]
    stock_service.execute_trade(conn, "0-1", "TECH", "buy", 5, now=0.0, actor="member",
                                tuning=cfg.tuning, noise_scale=0.0)
    assert stock_repo.get_holding(conn, "0-1", "TECH") == 5
    assert bank_repo.get_member(conn, "0-1")["balance"] == bal0 - int(round(p0 * 5))
    # total_market_shares is provisioned to market_share_baseline (equilibrium anchor); a buy of 5 adds to it
    baseline = stock_repo.get_stock(conn, "TECH")["market_share_baseline"]
    assert stock_repo.get_stock(conn, "TECH")["total_market_shares"] == baseline + 5


def test_buy_insufficient_cash_blocked():
    conn, cfg = _setup()
    import pytest
    with pytest.raises(ValueError):
        stock_service.execute_trade(conn, "0-1", "TECH", "buy", 100000, now=0.0,
                                    actor="member", tuning=cfg.tuning, noise_scale=0.0)


def test_sell_requires_shares():
    conn, cfg = _setup()
    import pytest
    with pytest.raises(ValueError):
        stock_service.execute_trade(conn, "0-1", "TECH", "sell", 1, now=0.0,
                                    actor="member", tuning=cfg.tuning, noise_scale=0.0)
