"""SQLite repository — the zero-setup default. FTS5 powers cross-session search."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import config
from models import Message, Session, User

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT DEFAULT '',
    preferences TEXT DEFAULT '{}',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT DEFAULT 'New chat',
    running_summary TEXT DEFAULT '',
    summarized_upto INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tokens INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(user_id, updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    message_id UNINDEXED,
    session_id UNINDEXED
);
"""

_STOPWORDS = {
    "what", "when", "where", "who", "why", "how", "the", "and", "for",
    "are", "was", "were", "does", "did", "you", "this", "that", "with",
    "about", "tell", "have", "has", "had", "been", "from", "your",
}


def _fts_query(text: str) -> str:
    """Build a safe FTS5 MATCH expression. Raw punctuation is a syntax error."""
    words = ["".join(c for c in w if c.isalnum()) for w in text.lower().split()]
    terms = [w for w in words if len(w) > 2 and w not in _STOPWORDS]
    # FTS5 does no stemming: "samosa" would miss the stored "samosas". A prefix
    # query bridges singular/plural, which callers mix constantly.
    return " OR ".join(f"{t}*" for t in terms)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    def __init__(self, path: str | None = None):
        self.path = path or config.SQLITE_PATH
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def init_db(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ── users ────────────────────────────
    def ensure_user(self, user_id, name=""):
        self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, name, created_at) VALUES (?,?,?)",
            (user_id, name, _now_iso()),
        )
        self.conn.commit()
        return self.get_user(user_id)

    def get_user(self, user_id):
        r = self.conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not r:
            return None
        return User(
            user_id=r["user_id"], name=r["name"] or "",
            preferences=json.loads(r["preferences"] or "{}"),
        )

    def set_user_name(self, user_id, name):
        self.ensure_user(user_id)
        self.conn.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))
        self.conn.commit()

    # ── sessions ─────────────────────────
    def _row_to_session(self, r):
        return Session(
            session_id=r["session_id"], user_id=r["user_id"], title=r["title"],
            running_summary=r["running_summary"] or "",
            summarized_upto=r["summarized_upto"] or 0,
            metadata=json.loads(r["metadata"] or "{}"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    def create_session(self, user_id, title="New chat"):
        sid, now = str(uuid.uuid4()), _now_iso()
        self.conn.execute(
            "INSERT INTO sessions (session_id, user_id, title, created_at, updated_at)"
            " VALUES (?,?,?,?,?)", (sid, user_id, title, now, now),
        )
        self.conn.commit()
        return self.get_session(sid)

    def get_session(self, session_id):
        r = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        return self._row_to_session(r) if r else None

    def list_sessions(self, user_id, limit=50):
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def rename_session(self, session_id, title):
        self.conn.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE session_id=?",
            (title, _now_iso(), session_id),
        )
        self.conn.commit()

    def delete_session(self, session_id):
        self.conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self.conn.execute(
            "DELETE FROM messages_fts WHERE session_id=?", (session_id,)
        )
        self.conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        self.conn.commit()

    def clear_session(self, session_id):
        self.conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self.conn.execute(
            "DELETE FROM messages_fts WHERE session_id=?", (session_id,)
        )
        self.conn.execute(
            "UPDATE sessions SET running_summary='', summarized_upto=0 WHERE session_id=?",
            (session_id,),
        )
        self.conn.commit()

    def update_summary(self, session_id, summary, upto):
        self.conn.execute(
            "UPDATE sessions SET running_summary=?, summarized_upto=? WHERE session_id=?",
            (summary, upto, session_id),
        )
        self.conn.commit()

    # ── messages ─────────────────────────
    def _row_to_message(self, r):
        return Message(
            message_id=r["message_id"], session_id=r["session_id"], seq=r["seq"],
            role=r["role"], content=r["content"], tokens=r["tokens"] or 0,
            metadata=json.loads(r["metadata"] or "{}"),
            created_at=r["created_at"],
        )

    def append_message(self, session_id, role, content, metadata=None):
        seq = self.conn.execute(
            "SELECT COALESCE(MAX(seq),0)+1 AS n FROM messages WHERE session_id=?",
            (session_id,),
        ).fetchone()["n"]
        mid, now = str(uuid.uuid4()), _now_iso()
        self.conn.execute(
            "INSERT INTO messages (message_id, session_id, seq, role, content,"
            " tokens, metadata, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (mid, session_id, seq, role, content, len(content) // 4,
             json.dumps(metadata or {}), now),
        )
        self.conn.execute(
            "INSERT INTO messages_fts (content, message_id, session_id) VALUES (?,?,?)",
            (content, mid, session_id),
        )
        self.conn.execute(
            "UPDATE sessions SET updated_at=? WHERE session_id=?", (now, session_id)
        )
        self.conn.commit()
        m = Message(
            message_id=mid, session_id=session_id, seq=seq, role=role,
            content=content, tokens=len(content) // 4, metadata=metadata or {},
        )
        try:
            from storage.typesense_search import get_search
            user_id = self.conn.execute(
                "SELECT user_id FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()["user_id"]
            get_search().index_message({
                "message_id": m.message_id,
                "session_id": m.session_id,
                "user_id": user_id,
                "role": m.role,
                "content": m.content,
                "created_at": int(m.created_at.timestamp()),
            })
        except Exception:
            pass  # indexing is best-effort; never block a write
        return m

    def recent_messages(self, session_id, limit):
        rows = self.conn.execute(
            "SELECT * FROM (SELECT * FROM messages WHERE session_id=?"
            " ORDER BY seq DESC LIMIT ?) ORDER BY seq ASC",
            (session_id, limit),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def all_messages(self, session_id):
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY seq ASC", (session_id,)
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def message_count(self, session_id):
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id=?", (session_id,)
        ).fetchone()["n"]

    def search_messages(self, user_id, query, exclude_session, limit):
        user_filter = "AND s.user_id = ?" if user_id else ""
        try:
            from storage.typesense_search import get_search, TypesenseUnavailable, TypesenseNotConfigured
            ids = get_search().search_message_ids(user_id, query, limit)
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = self.conn.execute(
                    f"""
                    SELECT m.* FROM messages m
                    JOIN sessions s ON s.session_id = m.session_id
                    WHERE m.message_id IN ({placeholders})
                      {user_filter}
                      AND m.session_id != ?
                      AND m.role = 'user'
                    """,
                    ((*ids, user_id, exclude_session) if user_id
                     else (*ids, exclude_session)),
                ).fetchall()
                if rows:
                    return [self._row_to_message(r) for r in rows]
        except (TypesenseUnavailable, TypesenseNotConfigured):
            pass  # fall back to FTS5 below

        match = _fts_query(query)
        if not match:
            return []
        rows = self.conn.execute(
            f"""
            SELECT m.* FROM messages_fts f
            JOIN messages m ON m.message_id = f.message_id
            JOIN sessions s ON s.session_id = m.session_id
            WHERE messages_fts MATCH ?
              {user_filter}
              AND m.session_id != ?
              AND m.role = 'user'
            ORDER BY rank LIMIT ?
            """,
            ((match, user_id, exclude_session, limit) if user_id
             else (match, exclude_session, limit)),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_callers(self, limit=200):
        rows = self.conn.execute(
            """
            SELECT s.user_id AS user_id,
                   COUNT(DISTINCT s.session_id) AS session_count,
                   COUNT(m.message_id) AS message_count,
                   MAX(s.updated_at) AS last_active
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.session_id
            GROUP BY s.user_id
            ORDER BY last_active DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def session_message_count(self, session_id):
        return self.message_count(session_id)

    def mark_session_ended(self, session_id):
        row = self.conn.execute(
            "SELECT metadata FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        meta = json.loads(row["metadata"] or "{}") if row else {}
        meta["ended"] = True
        self.conn.execute("UPDATE sessions SET metadata=? WHERE session_id=?",
                          (json.dumps(meta), session_id))
        self.conn.commit()
