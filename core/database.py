"""
Trade Blotter - Database layer

Manages the SQLite database connection and schema initialization.
This module provides the persistence layer used by the application's
trade, confirmation, user and audit services.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "trade_blotter.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK(role IN ('TRADER','OPERATIONS','SUPERVISOR')),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS counterparties (
    name TEXT PRIMARY KEY,
    lei TEXT NOT NULL,
    confirmation_channel TEXT NOT NULL DEFAULT 'EMAIL',
    confirmation_email TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    trade_time TEXT NOT NULL,
    trader TEXT NOT NULL,
    desk TEXT NOT NULL,
    product TEXT NOT NULL CHECK(product IN ('Bond','IRS','FX Forward')),
    instrument TEXT NOT NULL,
    counterparty TEXT NOT NULL,
    broker TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'BOOKED',
    confirmation_status TEXT NOT NULL DEFAULT 'NOT_GENERATED',
    comments TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(counterparty) REFERENCES counterparties(name)
);

CREATE TABLE IF NOT EXISTS bond_details (
    trade_id TEXT PRIMARY KEY,
    isin TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    face_amount REAL NOT NULL CHECK(face_amount > 0),
    clean_price REAL NOT NULL CHECK(clean_price >= 0),
    currency TEXT NOT NULL,
    maturity_date TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS irs_details (
    trade_id TEXT PRIMARY KEY,
    direction TEXT NOT NULL CHECK(direction IN ('PAY_FIXED','RECEIVE_FIXED')),
    notional REAL NOT NULL CHECK(notional > 0),
    currency TEXT NOT NULL,
    fixed_rate REAL NOT NULL CHECK(fixed_rate >= 0),
    floating_index TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    maturity_date TEXT NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fx_forward_details (
    trade_id TEXT PRIMARY KEY,
    currency_pair TEXT NOT NULL,
    buy_currency TEXT NOT NULL,
    buy_amount REAL NOT NULL CHECK(buy_amount > 0),
    sell_currency TEXT NOT NULL,
    sell_amount REAL NOT NULL CHECK(sell_amount > 0),
    forward_rate REAL NOT NULL CHECK(forward_rate > 0),
    value_date TEXT NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trade_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);
"""

@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        users = [
            ('USR-TRD-001','Alex Martin','TRADER',1),
            ('USR-TRD-002','Emma Laurent','TRADER',1),
            ('USR-TRD-003','Lucas Bernard','TRADER',1),
            ('USR-TRD-004','Sofia Moreau','TRADER',1),
            ('USR-OPS-001','Sophie Bernard','OPERATIONS',1),
            ('USR-OPS-002','Lucas Robert','OPERATIONS',1),
            ('USR-OPS-003','Camille Moreau','OPERATIONS',1),
            ('USR-OPS-004','Thomas Leroy','OPERATIONS',1),
            ('USR-SUP-001','Nicolas Dubois','SUPERVISOR',1),
            ('USR-SUP-002','Claire Fontaine','SUPERVISOR',1),
        ]
        con.executemany("INSERT OR IGNORE INTO users(user_id,full_name,role,active) VALUES (?,?,?,?)", users)
        cps = [
            ("Atlas Bank Demo","529900DEMOATLAS001","EMAIL","confirms@atlas-demo.invalid",1),
            ("Meridian Markets Demo","529900DEMOMERID001","EMAIL","ops@meridian-demo.invalid",1),
            ("Northstar Securities Demo","529900DEMONORTH001","EMAIL","confirmations@northstar-demo.invalid",1),
            ("Helios Capital Demo","529900DEMOHELIOS01","EMAIL","ops@helios-demo.invalid",1),
            ("Orion Bank Demo","529900DEMOORION001","EMAIL","confirms@orion-demo.invalid",1),
        ]
        con.executemany("""INSERT OR IGNORE INTO counterparties
            (name,lei,confirmation_channel,confirmation_email,active) VALUES (?,?,?,?,?)""", cps)

def reset_db():
    """Delete the local demo database and recreate the V4.1 schema."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
