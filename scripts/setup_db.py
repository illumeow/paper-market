#!/usr/bin/env python3
"""
setup_db.py — provision/reset CLI for paper-market database.

Provisions the SQLite DB with schema + members/stocks/events from config.toml + pins.csv.
Does NOT start the event clock (that's a later explicit staff action).
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent dir to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import db, repo
from app.config import load_config


def main(argv=None) -> int:
    """
    Provision the database with members, stocks, and events.

    Args:
        argv: Command-line arguments (if None, uses sys.argv[1:])

    Returns:
        0 on success, 1 on failure
    """
    parser = argparse.ArgumentParser(
        description="Provision/reset paper-market database"
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", "data/paper.db"),
        help="DB path (default: $DB_PATH or data/paper.db)"
    )
    parser.add_argument(
        "--config",
        default="config/config.toml",
        help="Config path (default: config/config.toml)"
    )
    parser.add_argument(
        "--pins",
        default="config/pins.csv",
        help="Pins CSV path (default: config/pins.csv)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing data before provisioning"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip interactive confirmation for --reset"
    )

    args = parser.parse_args(argv)

    # Load config
    cfg = load_config(args.config)

    # Handle --reset
    if args.reset:
        if not args.force:
            # Check if stdin is a TTY
            if sys.stdin.isatty():
                # Interactive mode: prompt for confirmation
                response = input(f"Reset {args.db}? This deletes all data. Type 'reset' to confirm: ")
                if response != "reset":
                    print("aborted")
                    return 1
            else:
                # Non-interactive: require --force
                print(f"Cannot reset {args.db} non-interactively without --force")
                return 1

        # Delete the DB file and its WAL/SHM siblings (but not :memory:)
        if args.db != ":memory:":
            for suffix in ["", "-wal", "-shm"]:
                path = args.db + suffix
                if os.path.exists(path):
                    os.unlink(path)

    # Ensure parent dir exists
    db_path = Path(args.db)
    if db_path != Path(":memory:") and db_path.parent != Path():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Connect and init schema
    conn = db.connect(args.db)
    db.init_schema(conn)

    # Provision (without clock)
    repo.provision(conn, cfg, pins_path=args.pins)

    # Print summary
    member_count = conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"]
    stock_count = conn.execute("SELECT COUNT(*) c FROM stocks").fetchone()["c"]
    event_count = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]

    print(f"Provisioned {member_count} members, {stock_count} stocks, {event_count} events")
    print("clock NOT started — start the event from the teller panel at kickoff.")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
