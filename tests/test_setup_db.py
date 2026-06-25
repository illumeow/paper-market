import sys
import os
import pytest
from pathlib import Path

# Add scripts dir to path so we can import setup_db
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import setup_db
import app.db as db
from app.config import load_config
from app import repo
from app.clock import event_start, set_event_start


def test_setup_provisions_without_clock(tmp_path):
    """setup_db.main should provision members/stocks/events but NOT set the clock."""
    db_path = str(tmp_path / "test.db")
    rc = setup_db.main([
        "--db", db_path,
        "--config", "config/config.toml",
        "--pins", "config/pins.csv",
        "--force"
    ])
    assert rc == 0

    # Verify the DB was created and provisioned
    conn = db.connect(db_path)
    assert conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 120
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 5
    assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] >= 1
    # Clock should NOT be set
    assert event_start(conn) is None
    conn.close()


def test_reset_wipes_then_reprovisions(tmp_path):
    """setup_db.main with --reset should wipe existing data and reprovision."""
    db_path = str(tmp_path / "test.db")

    # First provision
    rc1 = setup_db.main([
        "--db", db_path,
        "--config", "config/config.toml",
        "--pins", "config/pins.csv",
        "--force"
    ])
    assert rc1 == 0

    # Add a sentinel (set event start and add a news row)
    conn = db.connect(db_path)
    set_event_start(conn, 999.0)
    conn.execute("INSERT INTO news(text, ts, source) VALUES(?, ?, ?)",
                 ("sentinel news", 1234.5, "test"))
    conn.commit()

    # Verify sentinel is there
    assert event_start(conn) == 999.0
    assert conn.execute("SELECT COUNT(*) c FROM news").fetchone()["c"] == 1
    conn.close()

    # Now reset
    rc2 = setup_db.main([
        "--db", db_path,
        "--config", "config/config.toml",
        "--pins", "config/pins.csv",
        "--reset",
        "--force"
    ])
    assert rc2 == 0

    # Verify sentinel is gone and data is reseeded
    conn = db.connect(db_path)
    assert event_start(conn) is None
    assert conn.execute("SELECT COUNT(*) c FROM news").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"] == 120
    assert conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"] == 5
    conn.close()
