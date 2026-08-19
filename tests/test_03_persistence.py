"""Layer 3 — persistence.

Proves: conversations survive the process ending. This is the difference
between a chat toy and a chat product.
"""
import pytest

from providers.fake_provider import FakeProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore


def test_messages_survive_reconnect(tmp_path):
    """The core restart test: write with one connection, read with a new one."""
    db = str(tmp_path / "restart.db")

    repo1 = SQLiteStore(db)
    repo1.init_db()
    out = handle_message(repo1, FakeProvider("remembered"), "u1", None, "hello world")
    sid = out["session_id"]
    repo1.close()                                   # simulate process exit

    repo2 = SQLiteStore(db)                         # fresh connection
    repo2.init_db()
    msgs = repo2.all_messages(sid)
    assert len(msgs) == 2
    assert msgs[0].content == "hello world"
    assert msgs[1].content == "remembered"
    repo2.close()


def test_session_metadata_survives(tmp_path):
    db = str(tmp_path / "meta.db")
    repo1 = SQLiteStore(db); repo1.init_db()
    s = repo1.create_session("u1", "My Title")
    repo1.update_summary(s.session_id, "a summary", 4)
    repo1.close()

    repo2 = SQLiteStore(db); repo2.init_db()
    got = repo2.get_session(s.session_id)
    assert got.title == "My Title"
    assert got.running_summary == "a summary"
    assert got.summarized_upto == 4
    repo2.close()


def test_seq_continues_after_reconnect(tmp_path):
    """seq must keep counting, not restart at 1 on a new connection."""
    db = str(tmp_path / "seq.db")
    repo1 = SQLiteStore(db); repo1.init_db()
    s = repo1.create_session("u1")
    for i in range(3):
        repo1.append_message(s.session_id, "user", f"m{i}")
    repo1.close()

    repo2 = SQLiteStore(db); repo2.init_db()
    repo2.append_message(s.session_id, "user", "m3")
    seqs = [m.seq for m in repo2.all_messages(s.session_id)]
    assert seqs == [1, 2, 3, 4]
    repo2.close()


def test_ordering_is_by_seq_not_time(sqlite_repo):
    s = sqlite_repo.create_session("u1")
    for i in range(30):
        sqlite_repo.append_message(s.session_id, "user", f"msg-{i}")
    msgs = sqlite_repo.all_messages(s.session_id)
    assert [m.content for m in msgs] == [f"msg-{i}" for i in range(30)]


def test_recent_messages_returns_tail_in_order(sqlite_repo):
    s = sqlite_repo.create_session("u1")
    for i in range(20):
        sqlite_repo.append_message(s.session_id, "user", f"m{i}")
    recent = sqlite_repo.recent_messages(s.session_id, 5)
    assert [m.content for m in recent] == ["m15", "m16", "m17", "m18", "m19"]


def test_sqlite_and_memory_behave_identically(sqlite_repo, repo):
    """Both adapters must satisfy the same contract."""
    for store in (sqlite_repo, repo):
        s = store.create_session("u1", "T")
        store.append_message(s.session_id, "user", "hello")
        store.append_message(s.session_id, "assistant", "hi")
        assert store.message_count(s.session_id) == 2
        assert [m.role for m in store.all_messages(s.session_id)] == ["user", "assistant"]
        assert store.get_session(s.session_id).title == "T"
