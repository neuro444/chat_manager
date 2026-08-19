"""Layer 7 — rolling summary: long conversations compact without losing facts."""
import pytest
import config
from context.summary import maybe_roll_summary, should_roll
from providers.fake_provider import FakeProvider
from service import build_context, handle_message


def test_no_summary_for_short_conversation(repo):
    handle_message(repo, FakeProvider(), "u1", None, "hi")
    sid = repo.list_sessions("u1")[0].session_id
    assert repo.get_session(sid).running_summary == ""


def test_summary_rolls_after_threshold(repo):
    p = FakeProvider("SUMMARY: user discussed many topics.")
    sid = handle_message(repo, p, "u1", None, "turn 0")["session_id"]
    for i in range(1, 15):
        handle_message(repo, p, "u1", sid, f"turn {i}")
    assert repo.get_session(sid).running_summary != ""


def test_summarized_upto_advances(repo):
    p = FakeProvider("a summary")
    sid = handle_message(repo, p, "u1", None, "turn 0")["session_id"]
    for i in range(1, 15):
        handle_message(repo, p, "u1", sid, f"turn {i}")
    s = repo.get_session(sid)
    assert 0 < s.summarized_upto <= repo.message_count(sid)


def test_summary_reaches_the_prompt(repo):
    p = FakeProvider("DISTINCTIVE_SUMMARY_TOKEN")
    sid = handle_message(repo, p, "u1", None, "turn 0")["session_id"]
    for i in range(1, 15):
        handle_message(repo, p, "u1", sid, f"turn {i}")
    msgs = build_context(repo, "u1", sid, "next question")
    blob = "\n".join(m["content"] for m in msgs)
    assert "DISTINCTIVE_SUMMARY_TOKEN" in blob


def test_summary_survives_clear(repo):
    p = FakeProvider("s")
    sid = handle_message(repo, p, "u1", None, "t0")["session_id"]
    for i in range(1, 15):
        handle_message(repo, p, "u1", sid, f"t{i}")
    repo.clear_session(sid)
    assert repo.get_session(sid).running_summary == ""
    assert repo.get_session(sid).summarized_upto == 0
