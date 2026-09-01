"""Layer 23 — manager handoffs surfaced for the dashboard's approval column."""
import json

from api import _all_approvals, _message_result
from providers.fake_provider import FakeProvider
from service import handle_message


def _raw(answer, **flags):
    return json.dumps({
        "answer": answer, "call_ended": False, "order_ready": False,
        "order": None, "order_type": None, "user_name": None,
        "To_manager": False, "Transfer_to_Manager": False,
        "tools_called": False, "summary": "", "verbatim_user_chat": [],
        **flags,
    })


def _handoff(repo, user_id, summary="Office catering"):
    raw = _raw("Our manager will contact you.", call_ended=True, To_manager=True,
               order_type="catering", summary=summary,
               verbatim_user_chat=["I need catering"])
    return handle_message(repo, FakeProvider(raw), user_id, None, "catering")


def test_handoff_appears_as_a_pending_approval(repo):
    _handoff(repo, "+9177")
    rows = _all_approvals(repo)
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["order_type"] == "catering"
    assert rows[0]["summary"] == "Office catering"
    assert rows[0]["verbatim_user_chat"] == ["I need catering"]
    assert rows[0]["user_id"] == "+9177"
    assert rows[0]["requested_at"]


def test_a_plain_call_creates_no_approval(repo):
    handle_message(repo, FakeProvider(_raw("We open at nine.")), "+9100", None, "hours")
    assert _all_approvals(repo) == []


def test_message_result_defaults_to_no_handoff(repo):
    handle_message(repo, FakeProvider(_raw("Sure.")), "+9101", None, "hi")
    assistant = repo.all_messages(repo.list_sessions("+9101", limit=1)[0].session_id)[-1]
    result = _message_result(assistant)
    assert result["to_manager"] is False
    assert result["verbatim_user_chat"] == []


def test_approvals_are_newest_first(repo):
    _handoff(repo, "+9001", summary="First")
    _handoff(repo, "+9002", summary="Second")
    rows = _all_approvals(repo)
    assert len(rows) == 2
    assert rows[0]["requested_at"] >= rows[1]["requested_at"]
