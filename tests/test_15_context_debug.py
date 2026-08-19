"""Layer 15 — developer context printing.

Five labelled contexts printed to the console. The menu is abbreviated for the
developer's eyes only; the model must still receive it in full.
"""
import pytest

from context.debug import build_context_report, abbreviate
from providers.fake_provider import FakeProvider
from service import build_context, handle_message


def test_report_has_five_labelled_contexts(repo):
    handle_message(repo, FakeProvider(), "+9199", None, "two samosas")
    sid = repo.list_sessions("+9199")[0].session_id
    report = build_context_report(repo, "+9199", sid, "what is my total?")
    for label in ("1. USER QUERY", "2. CHAT SESSION HISTORY",
                  "3. RECENT SESSIONS", "4. ALL PAST CHATS SUMMARY",
                  "5. MENU"):
        assert label in report


def test_current_query_is_shown(repo):
    sid = repo.create_session("+9199").session_id
    report = build_context_report(repo, "+9199", sid, "DISTINCTIVE_QUERY")
    assert "DISTINCTIVE_QUERY" in report


def test_menu_is_abbreviated_in_report(repo):
    """Developer sees ~100 words; the model still gets all 153 items."""
    from menu.loader import format_menu_for_prompt
    sid = repo.create_session("+9199").session_id
    report = build_context_report(repo, "+9199", sid, "hi")
    full = format_menu_for_prompt()
    assert len(report) < len(full)
    assert "..." in report or "…" in report


def test_model_still_receives_full_menu(repo):
    """The abbreviation must never leak into what is actually sent."""
    from menu.loader import menu_items
    sid = repo.create_session("+9199").session_id
    msgs = build_context(repo, "+9199", sid, "hi")
    blob = "\n".join(m["content"] for m in msgs)
    for item in menu_items():
        assert item["name"] in blob


def test_abbreviate_keeps_head_and_tail_verbatim():
    text = "\n".join(f"line{i}" for i in range(200))
    short = abbreviate(text, words=100)
    assert short.startswith("line0")
    assert "line199" in short
    assert len(short.split()) < len(text.split())


def test_past_sessions_capped_at_twenty(repo):
    for i in range(30):
        s = repo.create_session("+9199", f"call {i}")
        repo.append_message(s.session_id, "user", f"order {i}")
    current = repo.create_session("+9199").session_id
    report = build_context_report(repo, "+9199", current, "hi")
    section = report.split("4. ALL PAST CHATS SUMMARY")[1]
    assert section.count("call ") <= 20


def test_report_survives_empty_session(repo):
    sid = repo.create_session("+9111").session_id
    report = build_context_report(repo, "+9111", sid, "first message")
    assert "1. USER QUERY" in report
