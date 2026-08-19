"""In-memory repository. Used by tests: no I/O, no fixtures to clean up."""
import uuid
from datetime import datetime, timezone

from models import Message, Session, User

_STOPWORDS = {
    "what", "when", "where", "who", "why", "how", "the", "a", "an", "is",
    "are", "was", "were", "do", "does", "did", "my", "me", "i", "you",
    "and", "or", "of", "to", "in", "on", "for", "it", "that", "this",
    "am", "be", "been", "have", "has", "had", "with", "about", "tell",
}


def _keywords(text: str) -> list[str]:
    return [w for w in "".join(
        c.lower() if c.isalnum() else " " for c in text
    ).split() if len(w) > 2 and w not in _STOPWORDS]


class MemoryStore:
    def __init__(self):
        self.users: dict[str, User] = {}
        self.sessions: dict[str, Session] = {}
        self.messages: dict[str, list[Message]] = {}

    def init_db(self) -> None:
        pass

    # ── users ────────────────────────────
    def ensure_user(self, user_id, name=""):
        if user_id not in self.users:
            self.users[user_id] = User(user_id=user_id, name=name)
        return self.users[user_id]

    def get_user(self, user_id):
        return self.users.get(user_id)

    def set_user_name(self, user_id, name):
        self.ensure_user(user_id)
        self.users[user_id].name = name

    # ── sessions ─────────────────────────
    def create_session(self, user_id, title="New chat"):
        s = Session(session_id=str(uuid.uuid4()), user_id=user_id, title=title)
        self.sessions[s.session_id] = s
        self.messages[s.session_id] = []
        return s

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def list_sessions(self, user_id, limit=50):
        mine = [s for s in self.sessions.values() if s.user_id == user_id]
        return sorted(mine, key=lambda s: s.updated_at, reverse=True)[:limit]

    def rename_session(self, session_id, title):
        if session_id in self.sessions:
            self.sessions[session_id].title = title

    def delete_session(self, session_id):
        self.sessions.pop(session_id, None)
        self.messages.pop(session_id, None)

    def clear_session(self, session_id):
        self.messages[session_id] = []
        if session_id in self.sessions:
            self.sessions[session_id].running_summary = ""
            self.sessions[session_id].summarized_upto = 0

    def update_summary(self, session_id, summary, upto):
        if session_id in self.sessions:
            self.sessions[session_id].running_summary = summary
            self.sessions[session_id].summarized_upto = upto

    # ── messages ─────────────────────────
    def append_message(self, session_id, role, content, metadata=None):
        msgs = self.messages.setdefault(session_id, [])
        m = Message(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            seq=len(msgs) + 1,
            role=role,
            content=content,
            tokens=len(content) // 4,
            metadata=metadata or {},
        )
        msgs.append(m)
        if session_id in self.sessions:
            self.sessions[session_id].updated_at = datetime.now(timezone.utc)
        return m

    def recent_messages(self, session_id, limit):
        return self.messages.get(session_id, [])[-limit:]

    def all_messages(self, session_id):
        return list(self.messages.get(session_id, []))

    def message_count(self, session_id):
        return len(self.messages.get(session_id, []))

    def search_messages(self, user_id, query, exclude_session, limit):
        terms = set(_keywords(query))
        if not terms:
            return []
        # scoping: only this user's sessions, excluding the current one
        mine = {sid for sid, s in self.sessions.items() if s.user_id == user_id}
        scored = []
        for sid in mine - {exclude_session}:
            for m in self.messages.get(sid, []):
                words = set(_keywords(m.content))
                overlap = sum(
                    1 for t in terms
                    if any(w.startswith(t) or t.startswith(w) for w in words)
                )
                if overlap:
                    scored.append((overlap, m))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def list_callers(self, limit=200):
        """Distinct callers (phone numbers) with activity counts, newest first."""
        out = {}
        for sess in self.sessions.values():
            row = out.setdefault(sess.user_id, {
                "user_id": sess.user_id, "session_count": 0,
                "message_count": 0, "last_active": sess.updated_at,
            })
            row["session_count"] += 1
            row["message_count"] += len(self.messages.get(sess.session_id, []))
            if sess.updated_at > row["last_active"]:
                row["last_active"] = sess.updated_at
        rows = sorted(out.values(), key=lambda r: r["last_active"], reverse=True)
        return rows[:limit]

    def session_message_count(self, session_id):
        return len(self.messages.get(session_id, []))

    def mark_session_ended(self, session_id):
        if session_id in self.sessions:
            self.sessions[session_id].metadata["ended"] = True
