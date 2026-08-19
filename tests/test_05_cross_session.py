"""Layer 5 — cross-session memory: recall facts from the user's OTHER sessions."""
import pytest
from providers.fake_provider import FakeProvider
from service import build_context, handle_message


@pytest.fixture(params=["memory", "sqlite"])
def store(request, repo, sqlite_repo):
    return repo if request.param == "memory" else sqlite_repo


def test_recalls_fact_from_previous_session(store):
    p = FakeProvider()
    handle_message(store, p, "u1", None,
                   "I am building a chat manager with Python and MongoDB")
    new_sid = store.create_session("u1").session_id
    msgs = build_context(store, "u1", new_sid, "what am I building?")
    blob = "\n".join(m["content"] for m in msgs)
    assert "chat manager" in blob.lower()


def test_no_memory_block_when_nothing_relevant(store):
    p = FakeProvider()
    handle_message(store, p, "u1", None, "the weather is nice today")
    new_sid = store.create_session("u1").session_id
    msgs = build_context(store, "u1", new_sid, "quantum chromodynamics equations")
    blob = "\n".join(m["content"] for m in msgs)
    assert "weather" not in blob.lower()


def test_current_session_excluded_from_memory(store):
    """Own history arrives via the history layer; it must not double up."""
    p = FakeProvider()
    sid = handle_message(store, p, "u1", None, "elephants are large")["session_id"]
    hits = store.search_messages("u1", "elephants", sid, 5)
    assert hits == []


def test_memory_survives_restart(tmp_path):
    from storage.sqlite_store import SQLiteStore
    db = str(tmp_path / "mem.db")
    r1 = SQLiteStore(db); r1.init_db()
    handle_message(r1, FakeProvider(), "u1", None, "my favourite language is Haskell")
    r1.close()

    r2 = SQLiteStore(db); r2.init_db()
    new_sid = r2.create_session("u1").session_id
    msgs = build_context(r2, "u1", new_sid, "what is my favourite language?")
    blob = "\n".join(m["content"] for m in msgs)
    r2.close()
    assert "haskell" in blob.lower()


def test_plural_singular_match(store):
    """Callers say "two samosas"; later they ask about "samosa". FTS5 does no
    stemming, so prefix matching is what bridges the two."""
    from providers.fake_provider import FakeProvider
    handle_message(store, FakeProvider(), "+919", None,
                   "I'll take two samosas and one gobi manchurian")
    new_sid = store.create_session("+919").session_id
    hits = store.search_messages("+919", "samosa", new_sid, 5)
    assert hits, "singular query must match the plural that was stored"


def test_past_order_recalled_from_vague_followup(store):
    """"What did I get last time?" carries no menu words — entity carry-over and
    retrieval must still surface the previous order."""
    from providers.fake_provider import FakeProvider
    from service import build_context
    handle_message(store, FakeProvider(), "+9110", None,
                   "I'll take two samosas and one gobi manchurian")
    new_sid = store.create_session("+9110").session_id
    blob = "\n".join(m["content"] for m in
                     build_context(store, "+9110", new_sid, "what did I get last time?"))
    assert "samosa" in blob.lower()
