"""Order approval decisions. Records whether a pending order was approved or rejected."""
import sqlite3
import os
from datetime import datetime, timezone

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
"""


def _conn():
    path = getattr(config, "SQLITE_PATH", None) or os.getenv("SQLITE_PATH", "chat_manager.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def set_decision(order_id: str, status: str) -> dict:
    """status must be 'approved' or 'rejected'."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute(
            "INSERT INTO approvals (order_id, status, decided_at) VALUES (?,?,?) "
            "ON CONFLICT(order_id) DO UPDATE SET status=excluded.status, decided_at=excluded.decided_at",
            (order_id, status, now),
        )
        c.commit()
    return {"order_id": order_id, "status": status, "decided_at": now}


def get_decisions() -> dict:
    """Return {order_id: status} for all decided orders."""
    with _conn() as c:
        rows = c.execute("SELECT order_id, status FROM approvals").fetchall()
    return {r["order_id"]: r["status"] for r in rows}


def get_status(order_id: str) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT status FROM approvals WHERE order_id=?", (order_id,)).fetchone()
    return row["status"] if row else None
