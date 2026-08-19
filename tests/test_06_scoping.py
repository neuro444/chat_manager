"""Layer 6 — user scoping. THE security test of this architecture.

If any of these fail, one user can see another user's private conversations.
"""
import pytest
from providers.fake_provider import FakeProvider
from service import build_context, handle_message


@pytest.fixture(params=["memory", "sqlite"])
def store(request, repo, sqlite_repo):
    return repo if request.param == "memory" else sqlite_repo


def test_search_never_returns_another_users_messages(store):
    handle_message(store, FakeProvider(), "alice", None,
                   "my secret project is called Falcon")
    bob_sid = store.create_session("bob").session_id
    hits = store.search_messages("bob", "Falcon secret project", bob_sid, 10)
    assert hits == [], "Bob must never see Alice's messages"


def test_assembled_context_never_leaks_across_users(store):
    handle_message(store, FakeProvider(), "alice", None,
                   "my password hint is bluebird")
    bob_sid = store.create_session("bob").session_id
    msgs = build_context(store, "bob", bob_sid, "what is my password hint?")
    blob = "\n".join(m["content"] for m in msgs)
    assert "bluebird" not in blob.lower()


def test_same_user_does_see_own_history(store):
    """The mirror of the leak test — scoping must not over-block."""
    handle_message(store, FakeProvider(), "alice", None,
                   "my secret project is called Falcon")
    alice_sid2 = store.create_session("alice").session_id
    msgs = build_context(store, "alice", alice_sid2, "what is my project called?")
    blob = "\n".join(m["content"] for m in msgs)
    assert "falcon" in blob.lower()


def test_sessions_list_never_shows_other_users(store):
    handle_message(store, FakeProvider(), "alice", None, "hi")
    handle_message(store, FakeProvider(), "bob", None, "hi")
    alice_ids = {s.session_id for s in store.list_sessions("alice")}
    bob_ids = {s.session_id for s in store.list_sessions("bob")}
    assert alice_ids.isdisjoint(bob_ids)
