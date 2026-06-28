import hashlib
import app.core.db as db
from app.core.config import load_config
from app.core import provision
from app.bank import repo as bank_repo
from app.stock import repo as stock_repo
from app.core.clock import event_start


def test_provision_seeds_without_clock(tmp_path):
    """provision should seed members/stocks/events but NOT set the clock."""
    pins = tmp_path / "pins.csv"
    pins.write_text("member_id,pin\n" + "".join(f"{g}-{i},{1000+g*12+i}\n"
                    for g in range(10) for i in range(1, 13)))
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    provision.provision(conn, cfg, pins_path=str(pins), now=1000.0)
    assert conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 120
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 5
    assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] >= 1
    # Clock should NOT be set by provision
    assert event_start(conn) is None


def test_provision_idempotent(tmp_path):
    """provision should be idempotent: calling twice leaves counts unchanged."""
    pins = tmp_path / "pins.csv"
    pins.write_text("member_id,pin\n" + "".join(f"{g}-{i},{1000+g*12+i}\n"
                    for g in range(10) for i in range(1, 13)))
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    provision.provision(conn, cfg, pins_path=str(pins), now=1000.0)
    provision.provision(conn, cfg, pins_path=str(pins), now=2000.0)
    assert conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 120
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 5


def test_seed_still_sets_clock(tmp_path):
    """seed should still set the clock when it is None."""
    pins = tmp_path / "pins.csv"
    pins.write_text("member_id,pin\n" + "".join(f"{g}-{i},{1000+g*12+i}\n"
                    for g in range(10) for i in range(1, 13)))
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    provision.seed(conn, cfg, pins_path=str(pins), now=1234.0)
    assert event_start(conn) == 1234.0


def test_seed_members_stocks_idempotent(tmp_path):
    pins = tmp_path / "pins.csv"
    pins.write_text("member_id,pin\n" + "".join(f"{g}-{i},{1000+g*12+i}\n"
                    for g in range(10) for i in range(1, 13)))
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    provision.seed(conn, cfg, pins_path=str(pins), now=1000.0)
    provision.seed(conn, cfg, pins_path=str(pins), now=2000.0)  # idempotent
    assert conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 120
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 5
    # Provision hashes PINs: member 0-1 has PIN "1001", stored as its sha256 hash.
    expected = hashlib.sha256(b"1001").hexdigest()
    assert bank_repo.get_member(conn, "0-1")["pin"] == expected
    # event start fixed on first seed
    assert event_start(conn) == 1000.0


def test_provision_sets_total_market_shares_to_market_share_baseline(tmp_path):
    """Freshly provisioned stocks must have total_market_shares == market_share_baseline so supply_pressure is 0."""
    pins = tmp_path / "pins.csv"
    pins.write_text("member_id,pin\n" + "".join(f"{g}-{i},{1000+g*12+i}\n"
                    for g in range(10) for i in range(1, 13)))
    conn = db.connect(":memory:"); db.init_schema(conn)
    cfg = load_config()
    provision.provision(conn, cfg, pins_path=str(pins), now=1000.0)
    for s in cfg.stocks:
        row = conn.execute("SELECT market_share_baseline, total_market_shares FROM stocks WHERE stock_id=?",
                           (s["id"],)).fetchone()
        assert row["total_market_shares"] == s["market_share_baseline"], (
            f"{s['id']}: expected total_market_shares={s['market_share_baseline']}, got {row['total_market_shares']}")
        # supply_pressure = -reversion_strength * (total_market_shares - market_share_baseline) / pressure_normalizer == 0
        assert row["total_market_shares"] - row["market_share_baseline"] == 0


def test_add_news_round_trips_columns():
    conn = db.connect(":memory:"); db.init_schema(conn)
    stock_repo.add_news(conn, "Big news", "event", 1234.5)
    row = stock_repo.current_news(conn, limit=1)[0]
    assert row["text"] == "Big news"
    assert row["source"] == "event"
    assert row["ts"] == 1234.5


def test_news_after_cursor_delivers_each_row_once():
    # models the ticker's last_news_id cursor: each row is seen exactly once, in order
    conn = db.connect(":memory:"); db.init_schema(conn)
    assert stock_repo.latest_news_id(conn) == 0          # empty -> cursor starts at 0
    assert stock_repo.news_after(conn, 0) == []

    stock_repo.add_news(conn, "first", "event", 1.0)
    fresh = stock_repo.news_after(conn, 0)
    assert [r["text"] for r in fresh] == ["first"]
    cursor = fresh[-1]["id"]

    # nothing new -> the same news is NOT re-delivered (the reported banner bug)
    assert stock_repo.news_after(conn, cursor) == []

    stock_repo.add_news(conn, "second", "manual", 2.0)
    fresh2 = stock_repo.news_after(conn, cursor)
    assert [r["text"] for r in fresh2] == ["second"]
    assert stock_repo.latest_news_id(conn) == fresh2[-1]["id"]
