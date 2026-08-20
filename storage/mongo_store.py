"""MongoDB repository — the production choice (handles concurrent writes).

Creates its own database and indexes on first use; never touches other DBs.
"""
import uuid
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient, TEXT

import config
from models import Message, Session, User


def _now():
    return datetime.now(timezone.utc)


class MongoStore:
    def __init__(self, uri: str | None = None, db_name: str | None = None):
        self.client = MongoClient(uri or config.MONGO_URI,
                                  serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or config.MONGO_DB]

    def init_db(self) -> None:
        self.db.messages.create_index([("session_id", ASCENDING), ("seq", ASCENDING)])
        self.db.messages.create_index([("content", TEXT)])
        self.db.sessions.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])

    def close(self) -> None:
        self.client.close()

    # ── users ────────────────────────────
    def ensure_user(self, user_id, name=""):
        self.db.users.update_one(
            {"_id": user_id},
            {"$setOnInsert": {"name": name, "preferences": {}, "created_at": _now()}},
            upsert=True,
        )
        return self.get_user(user_id)

    def get_user(self, user_id):
        d = self.db.users.find_one({"_id": user_id})
        if not d:
            return None
        return User(user_id=user_id, name=d.get("name", ""),
                    preferences=d.get("preferences", {}))

    def set_user_name(self, user_id, name):
        self.ensure_user(user_id)
        self.db.users.update_one({"_id": user_id}, {"$set": {"name": name}})

    def delete_user(self, user_id):
        session_ids = [doc["_id"] for doc in self.db.sessions.find(
            {"user_id": user_id}, {"_id": 1}
        )]
        if session_ids:
            self.db.messages.delete_many({"session_id": {"$in": session_ids}})
            self.db.counters.delete_many({"_id": {"$in": session_ids}})
            self.db.sessions.delete_many({"_id": {"$in": session_ids}})
        self.db.users.delete_one({"_id": user_id})

    # ── sessions ─────────────────────────
    def _to_session(self, d):
        return Session(
            session_id=d["_id"], user_id=d["user_id"], title=d.get("title", "New chat"),
            running_summary=d.get("running_summary", ""),
            summarized_upto=d.get("summarized_upto", 0),
            metadata=d.get("metadata", {}),
        )

    def create_session(self, user_id, title="New chat"):
        sid, now = str(uuid.uuid4()), _now()
        self.db.sessions.insert_one({
            "_id": sid, "user_id": user_id, "title": title,
            "running_summary": "", "summarized_upto": 0, "metadata": {},
            "created_at": now, "updated_at": now,
        })
        return self.get_session(sid)

    def get_session(self, session_id):
        d = self.db.sessions.find_one({"_id": session_id})
        return self._to_session(d) if d else None

    def list_sessions(self, user_id, limit=50):
        cur = self.db.sessions.find({"user_id": user_id}) \
            .sort("updated_at", DESCENDING).limit(limit)
        return [self._to_session(d) for d in cur]

    def rename_session(self, session_id, title):
        self.db.sessions.update_one({"_id": session_id},
                                    {"$set": {"title": title, "updated_at": _now()}})

    def delete_session(self, session_id):
        self.db.messages.delete_many({"session_id": session_id})
        self.db.sessions.delete_one({"_id": session_id})
        self.db.counters.delete_one({"_id": session_id})

    def clear_session(self, session_id):
        self.db.messages.delete_many({"session_id": session_id})
        self.db.counters.delete_one({"_id": session_id})
        self.db.sessions.update_one(
            {"_id": session_id},
            {"$set": {"running_summary": "", "summarized_upto": 0}},
        )

    def update_summary(self, session_id, summary, upto):
        self.db.sessions.update_one(
            {"_id": session_id},
            {"$set": {"running_summary": summary, "summarized_upto": upto}},
        )

    # ── messages ─────────────────────────
    def _to_message(self, d):
        return Message(
            message_id=d["_id"], session_id=d["session_id"], seq=d["seq"],
            role=d["role"], content=d["content"], tokens=d.get("tokens", 0),
            metadata=d.get("metadata", {}),
        )

    def _next_seq(self, session_id) -> int:
        """Atomic counter — MAX(seq)+1 races under concurrent writes."""
        doc = self.db.counters.find_one_and_update(
            {"_id": session_id}, {"$inc": {"seq": 1}},
            upsert=True, return_document=True,
        )
        return doc["seq"]

    def append_message(self, session_id, role, content, metadata=None):
        mid, now = str(uuid.uuid4()), _now()
        seq = self._next_seq(session_id)
        self.db.messages.insert_one({
            "_id": mid, "session_id": session_id, "seq": seq, "role": role,
            "content": content, "tokens": len(content) // 4,
            "metadata": metadata or {}, "created_at": now,
        })
        self.db.sessions.update_one({"_id": session_id},
                                    {"$set": {"updated_at": now}})
        return Message(message_id=mid, session_id=session_id, seq=seq, role=role,
                       content=content, tokens=len(content) // 4,
                       metadata=metadata or {})

    def recent_messages(self, session_id, limit):
        cur = self.db.messages.find({"session_id": session_id}) \
            .sort("seq", DESCENDING).limit(limit)
        return list(reversed([self._to_message(d) for d in cur]))

    def all_messages(self, session_id):
        cur = self.db.messages.find({"session_id": session_id}).sort("seq", ASCENDING)
        return [self._to_message(d) for d in cur]

    def message_count(self, session_id):
        return self.db.messages.count_documents({"session_id": session_id})

    def search_messages(self, user_id, query, exclude_session, limit):
        my_sessions = [s["_id"] for s in
                       self.db.sessions.find({"user_id": user_id}, {"_id": 1})]
        targets = [s for s in my_sessions if s != exclude_session]
        if not targets:
            return []
        cur = self.db.messages.find(
            {"$text": {"$search": query},
             "session_id": {"$in": targets},      # scoping enforced here
             "role": "user"},
            {"score": {"$meta": "textScore"}, "_id": 1, "session_id": 1, "seq": 1,
             "role": 1, "content": 1, "tokens": 1, "metadata": 1},
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        return [self._to_message(d) for d in cur]

    def list_callers(self, limit=200):
        rows = {}
        for d in self.db.sessions.find():
            r = rows.setdefault(d["user_id"], {
                "user_id": d["user_id"], "session_count": 0,
                "message_count": 0, "last_active": d.get("updated_at"),
            })
            r["session_count"] += 1
            r["message_count"] += self.db.messages.count_documents(
                {"session_id": d["_id"]})
            if d.get("updated_at") and d["updated_at"] > r["last_active"]:
                r["last_active"] = d["updated_at"]
        out = sorted(rows.values(), key=lambda r: r["last_active"], reverse=True)
        return out[:limit]

    def session_message_count(self, session_id):
        return self.message_count(session_id)

    def mark_session_ended(self, session_id):
        self.db.sessions.update_one({"_id": session_id},
                                    {"$set": {"metadata.ended": True}})
