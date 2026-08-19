"""Layer 17 — structured call flow flags and persistence."""
import json

from context.callflow import parse_model_response


def _raw(answer, **flags):
    return json.dumps({
        "answer": answer,
        "call_ended": False,
        "order_ready": False,
        "order": None,
        "To_manager": False,
        "Transfer_to_Manager": False,
        "tools_called": False,
        "summary": "",
        "verbatim_user_chat": [],
        **flags,
    })


def test_json_response_is_parsed():
    out = parse_model_response(_raw("Order confirmed.", call_ended=True,
                                    order_ready=True, tools_called=True))
    assert out["answer"] == "Order confirmed."
    assert out["call_ended"] is True
    assert out["order_ready"] is True
    assert out["tools_called"] is True


def test_plain_text_fallback_never_infers_action_flags():
    out = parse_model_response("still ordering")
    assert out["answer"] == "still ordering"
    assert out["call_ended"] is False
    assert out["order_ready"] is False
    assert out["order"] is None
    assert out["To_manager"] is False
    assert out["Transfer_to_Manager"] is False


def test_order_flags_are_returned_and_persisted(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Order confirmed. CakeWorld Alpharetta.", call_ended=True,
               order_ready=True, tools_called=True)
    priced = {"name": "price_order", "result": {
        "items": [{"name": "Veg Biriyani", "price": 13.99,
                   "quantity": 3, "line_total": 41.97}],
        "unknown": [], "subtotal": 41.97, "tax": 3.25, "total": 45.22,
    }}
    out = handle_message(repo, FakeProvider(raw, [priced]), "+9188", None,
                         "pickup")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["order_ready"] is True
    assert out["order"]["items"][0]["unit_price"] == "13.99"
    assert out["order"]["total"] == "45.22"
    assert out["To_manager"] is False
    assert out["tools_called"] is True
    assert assistant.metadata["order_ready"] is True
    assert assistant.metadata["order"] == out["order"]
    assert assistant.metadata["tools_called"] is True


def test_manager_flag_is_returned_and_persisted(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Our manager will contact you.", call_ended=True,
               To_manager=True, summary="Office catering",
               verbatim_user_chat=["I need catering"])
    out = handle_message(repo, FakeProvider(raw), "+9177", None, "catering")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["order_ready"] is False
    assert out["To_manager"] is True
    assert out["summary"] == "Office catering"
    assert assistant.metadata["To_manager"] is True


def test_direct_manager_transfer_is_returned_and_persisted(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("I'll connect you with restaurant staff.",
               Transfer_to_Manager=True,
               summary="Customer disputes a charge and requests a refund.")
    out = handle_message(repo, FakeProvider(raw), "+9177", None,
                         "I want a refund and need a manager")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["Transfer_to_Manager"] is True
    assert out["To_manager"] is False
    assert out["call_ended"] is False
    assert assistant.metadata["response_fields"]["Transfer_to_Manager"] is True


def test_new_prompt_json_fields_pass_through_without_service_mapping(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    out = handle_message(
        repo, FakeProvider(_raw("One moment.", future_control="example")),
        "+9177", None, "help",
    )
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["future_control"] == "example"
    assert assistant.metadata["response_fields"]["future_control"] == "example"


def test_session_marked_ended_from_json(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    out = handle_message(repo, FakeProvider(_raw("Done.", call_ended=True)),
                         "+9199", None, "that's all")
    assert repo.get_session(out["session_id"]).metadata.get("ended") is True


def test_open_call_is_not_marked_ended(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    out = handle_message(repo, FakeProvider(_raw("Anything else?")),
                         "+9199", None, "two samosas")
    assert not repo.get_session(out["session_id"]).metadata.get("ended")


def test_ended_session_is_not_resumed(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    first = handle_message(repo, FakeProvider(_raw("Bye.", call_ended=True)),
                           "+9199", None, "done")["session_id"]
    second = handle_message(repo, FakeProvider(_raw("Hello")), "+9199", None,
                            "new call")["session_id"]
    assert second != first


def test_prompt_states_delivery_and_json_contract():
    from prompts import SYSTEM_PROMPT

    assert "cakeworldeatery.com" in SYSTEM_PROMPT
    assert "CakeWorld Alpharetta" in SYSTEM_PROMPT
    assert "order_ready" in SYSTEM_PROMPT
    assert "tools_called" in SYSTEM_PROMPT
    assert "Transfer_to_Manager" in SYSTEM_PROMPT
    assert "[[END_CALL]]" not in SYSTEM_PROMPT


def test_model_cannot_mark_order_ready_without_actual_pricing_tool(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Order confirmed.", order_ready=True, tools_called=True)
    out = handle_message(repo, FakeProvider(raw), "+9188", None, "pickup")
    assert out["order_ready"] is False
    assert out["order"] is None
    assert out["tools_called"] is False
