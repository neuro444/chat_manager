"""Layer 2 — session memory.

Proves: within one session, turn 2 sees what turn 1 said. This is the layer
that makes a stateless LLM behave like it remembers.
"""
import pytest

from providers.fake_provider import FakeProvider
from service import handle_message
from storage.memory_store import MemoryStore


@pytest.fixture
def repo():
    r = MemoryStore()
    r.init_db()
    return r


def test_first_turn_creates_session(repo):
    out = handle_message(repo, FakeProvider(), "u1", None, "hello")
    assert out["session_id"]
    assert repo.get_session(out["session_id"]) is not None


def test_user_and_assistant_turns_are_persisted(repo):
    out = handle_message(repo, FakeProvider("hi there"), "u1", None, "hello")
    msgs = repo.all_messages(out["session_id"])
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "hello"
    assert msgs[1].content == "hi there"
    assert msgs[1].metadata["model"]
    assert isinstance(msgs[1].metadata["llm_latency_ms"], float)
    assert msgs[1].metadata["llm_latency_ms"] >= 0


def test_second_turn_receives_first_turn_as_history(repo):
    provider = FakeProvider("ok")
    out = handle_message(repo, provider, "u1", None, "my name is Sree")
    handle_message(repo, provider, "u1", out["session_id"], "what is my name?")

    sent = "\n".join(m["content"] for m in provider.last_messages)
    assert "my name is Sree" in sent, "turn 1 must appear in turn 2's context"


def test_current_message_is_not_duplicated(repo):
    """Guards the classic bug: message written to DB then appended again."""
    provider = FakeProvider()
    handle_message(repo, provider, "u1", None, "unique-phrase-xyz")
    hits = [m for m in provider.last_messages if m["content"] == "unique-phrase-xyz"]
    assert len(hits) == 1, f"sent {len(hits)} times, expected exactly 1"


def test_seq_is_monotonic(repo):
    out = handle_message(repo, FakeProvider(), "u1", None, "m0")
    sid = out["session_id"]
    for i in range(1, 10):
        handle_message(repo, FakeProvider(), "u1", sid, f"m{i}")
    seqs = [m.seq for m in repo.all_messages(sid)]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))


def test_history_window_is_capped(repo):
    """Old turns must drop out of context, or cost grows without bound."""
    import config
    provider = FakeProvider()
    out = handle_message(repo, provider, "u1", None, "turn-0")
    sid = out["session_id"]
    for i in range(1, 40):
        handle_message(repo, provider, "u1", sid, f"turn-{i}")

    turn_msgs = [m for m in provider.last_messages if m["role"] in ("user", "assistant")]
    assert len(turn_msgs) <= config.HISTORY_WINDOW + 1


def test_title_set_from_first_message(repo):
    out = handle_message(repo, FakeProvider(), "u1", None, "Explain vector databases")
    assert repo.get_session(out["session_id"]).title.startswith("Explain vector")
