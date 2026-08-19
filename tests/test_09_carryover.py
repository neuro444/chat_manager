"""Layer 9 — entity carry-over: short follow-ups resolve to the prior subject."""
import pytest
from context.state import extract_entities, resolve_active_entities
from providers.fake_provider import FakeProvider
from service import handle_message


@pytest.mark.parametrize("text,expected", [
    ("Tell me about Paris", ["Paris"]),
    ("Compare Tokyo and Berlin", ["Tokyo", "Berlin"]),
    ("what is the weather", []),
    ("yes", []),
    ("The quick brown fox", []),
])
def test_entity_extraction(text, expected):
    assert extract_entities(text) == expected


def test_followup_inherits_previous_entity(repo):
    p = FakeProvider()
    sid = handle_message(repo, p, "u1", None, "Tell me about Paris")["session_id"]
    assert resolve_active_entities(repo, sid, "what is the weather there?") == ["Paris"]


def test_explicit_entity_overrides_inherited(repo):
    p = FakeProvider()
    sid = handle_message(repo, p, "u1", None, "Tell me about Paris")["session_id"]
    assert resolve_active_entities(repo, sid, "Now tell me about Rome") == ["Rome"]


def test_never_invents_entities(repo):
    """The hard rule: with nothing prior, return nothing."""
    sid = repo.create_session("u1").session_id
    assert resolve_active_entities(repo, sid, "yes") == []


def test_carryover_scans_back_multiple_turns(repo):
    p = FakeProvider()
    sid = handle_message(repo, p, "u1", None, "Tell me about Iceland")["session_id"]
    handle_message(repo, p, "u1", sid, "ok")
    handle_message(repo, p, "u1", sid, "sure")
    assert resolve_active_entities(repo, sid, "and the weather?") == ["Iceland"]
