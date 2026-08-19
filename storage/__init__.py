"""Storage factory."""
import config


def make_repo(kind: str | None = None):
    kind = kind or config.STORAGE
    if kind == "sqlite":
        from .sqlite_store import SQLiteStore
        return SQLiteStore()
    if kind == "mongo":
        from .mongo_store import MongoStore
        return MongoStore()
    if kind == "memory":
        from .memory_store import MemoryStore
        return MemoryStore()
    raise ValueError(f"Unknown storage: {kind}")
