import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS members(
  member_id TEXT PRIMARY KEY, pin TEXT UNIQUE NOT NULL,
  balance INTEGER NOT NULL, balance_accrued_at REAL NOT NULL,
  debt INTEGER NOT NULL DEFAULT 0, loan_taken_at REAL,
  relief_claimed INTEGER NOT NULL DEFAULT 0, last_teller_visit_at REAL);
CREATE TABLE IF NOT EXISTS fixed_deposits(
  fd_id TEXT PRIMARY KEY, member_id TEXT NOT NULL, principal INTEGER NOT NULL,
  term_minutes INTEGER NOT NULL, rate_per_min REAL NOT NULL, created_at REAL NOT NULL,
  matured INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS holdings(
  member_id TEXT NOT NULL, stock_id TEXT NOT NULL, shares INTEGER NOT NULL,
  PRIMARY KEY (member_id, stock_id));
CREATE TABLE IF NOT EXISTS stocks(
  stock_id TEXT PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL,
  quarter_open_price REAL NOT NULL, band_floor_pct REAL NOT NULL, band_ceiling_pct REAL NOT NULL,
  flow_momentum REAL NOT NULL DEFAULT 0, total_market_shares INTEGER NOT NULL DEFAULT 0,
  trade_count INTEGER NOT NULL DEFAULT 0, floor REAL NOT NULL, ceiling REAL NOT NULL,
  pressure_normalizer INTEGER NOT NULL, market_share_baseline INTEGER NOT NULL, init_price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS price_history(stock_id TEXT, ts REAL, price REAL);
CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY AUTOINCREMENT, member_id TEXT, stock_id TEXT,
  side TEXT, shares INTEGER, price REAL, ts REAL, actor TEXT);
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, member_id TEXT, type TEXT,
  amount INTEGER, ts REAL, actor TEXT);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at_min REAL, stock_id TEXT, pct REAL,
  duration_min REAL, headline TEXT, fired INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS news(
  id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, ts REAL, source TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()
