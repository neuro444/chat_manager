"""Shared fixtures."""
import pytest

from providers.fake_provider import FakeProvider
from storage.memory_store import MemoryStore


@pytest.fixture
def repo():
    r = MemoryStore()
    r.init_db()
    return r


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def sqlite_repo(tmp_path):
    """A real SQLite DB in a temp dir, destroyed after the test."""
    from storage.sqlite_store import SQLiteStore
    r = SQLiteStore(str(tmp_path / "test.db"))
    r.init_db()
    yield r
    r.close()
