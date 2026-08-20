"""Layer 4 — multiple sessions: isolation + list/rename/delete/clear."""
import pytest
from providers.fake_provider import FakeProvider
from service import handle_message


@pytest.fixture(params=["memory", "sqlite"])
def store(request, repo, sqlite_repo):
    """Every session test runs against BOTH adapters."""
    return repo if request.param == "memory" else sqlite_repo


def test_sessions_are_isolated(store):
    """Two separate calls (explicit new sessions) must not share messages."""
    p = FakeProvider()
    a = handle_message(store, p, "u1", store.create_session("u1").session_id,
                       "apples")["session_id"]
    b = handle_message(store, p, "u1", store.create_session("u1").session_id,
                       "oranges")["session_id"]
    assert a != b
    assert [m.content for m in store.all_messages(a)][0] == "apples"
    assert [m.content for m in store.all_messages(b)][0] == "oranges"


def test_list_sessions_newest_first(store):
    p = FakeProvider()
    handle_message(store, p, "u1", store.create_session("u1").session_id, "first")
    second = handle_message(store, p, "u1", store.create_session("u1").session_id,
                            "second")["session_id"]
    sessions = store.list_sessions("u1")
    assert len(sessions) == 2
    assert sessions[0].session_id == second


def test_list_sessions_is_scoped_to_user(store):
    p = FakeProvider()
    handle_message(store, p, "alice", None, "alice msg")
    handle_message(store, p, "bob", None, "bob msg")
    assert len(store.list_sessions("alice")) == 1
    assert len(store.list_sessions("bob")) == 1


def test_rename_session(store):
    sid = handle_message(store, FakeProvider(), "u1", None, "hi")["session_id"]
    store.rename_session(sid, "Renamed Chat")
    assert store.get_session(sid).title == "Renamed Chat"


def test_delete_session_removes_messages(store):
    sid = handle_message(store, FakeProvider(), "u1", None, "hi")["session_id"]
    store.delete_session(sid)
    assert store.get_session(sid) is None
    assert store.all_messages(sid) == []


def test_delete_user_removes_profile_sessions_and_messages(store):
    first = handle_message(store, FakeProvider(), "u1", None, "first")
    second = handle_message(store, FakeProvider(), "u1", None, "second")
    store.delete_user("u1")
    assert store.get_user("u1") is None
    assert store.list_sessions("u1") == []
    assert store.all_messages(first["session_id"]) == []
    assert store.all_messages(second["session_id"]) == []


def test_clear_session_keeps_session_drops_messages(store):
    sid = handle_message(store, FakeProvider(), "u1", None, "hi")["session_id"]
    store.update_summary(sid, "old summary", 2)
    store.clear_session(sid)
    assert store.get_session(sid) is not None
    assert store.all_messages(sid) == []
    assert store.get_session(sid).running_summary == ""


def test_switching_back_resumes_history(store):
    p = FakeProvider()
    a = handle_message(store, p, "u1", None, "in session A")["session_id"]
    handle_message(store, p, "u1", None, "in session B")
    handle_message(store, p, "u1", a, "back in A")
    contents = [m.content for m in store.all_messages(a)]
    assert "in session A" in contents and "back in A" in contents


def test_missing_session_id_always_starts_new_call(store):
    """Isolation is backend-enforced for every client, including terminal calls."""
    p = FakeProvider()
    first = handle_message(store, p, "+919999999999", None, "one dosa")["session_id"]
    again = handle_message(store, p, "+919999999999", None, "and a chai")["session_id"]
    assert again != first
