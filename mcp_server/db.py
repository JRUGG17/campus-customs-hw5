"""Database paths, the extra tables the agents need, and the reset to the original.

data/campus_customs.db is the original and is only ever opened read-only.
data/campus_customs_new.db is the working copy that the MCP tools update.
"""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data" / "campus_customs.db"
WORKING = Path(os.getenv("CAMPUS_DB", ROOT / "data" / "campus_customs_new.db"))

# Tables the original database doesn't have. They live only in the working copy and are
# recreated by ensure_schema() after every reset.
EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',   -- prepared, ordered
    ticket_id INTEGER,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                        -- invoice_payment, rent_payment, purchase_order
    ref_id INTEGER NOT NULL,                   -- invoice id, lease id, or purchase order id
    amount REAL NOT NULL,
    description TEXT,
    ticket_id INTEGER,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',    -- pending, approved, rejected, executed
    decided_by TEXT,                           -- the human who approved or rejected
    decided_at TEXT,
    executed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    audience TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(EXTRA_SCHEMA)


def reset_working_copy() -> Path:
    """Replace the working copy with the original's values, then add the extra tables."""
    if WORKING.resolve() == ORIGINAL.resolve():
        raise RuntimeError("Refusing to reset: the working copy path is the original database.")
    src = sqlite3.connect(f"file:{ORIGINAL}?mode=ro", uri=True)
    dst = sqlite3.connect(WORKING)
    try:
        src.backup(dst)
        ensure_schema(dst)
        dst.commit()
    finally:
        src.close()
        dst.close()
    return WORKING


if __name__ == "__main__":
    print(f"Reset {reset_working_copy()} from {ORIGINAL}")
