"""Layer 17 — structured call flow flags and persistence."""
import json

from context.callflow import parse_model_response


def _raw(answer, **flags):
    return json.dumps({
        "answer": answer,
        "call_ended": False,
        "order_ready": False,
        "order": None,
        "order_type": None,
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
               order_ready=True, order_type="pickup", tools_called=True)
    priced = {"name": "price_order", "result": {
        "items": [{"name": "Veg Biriyani", "price": 13.99,
                   "quantity": 3, "line_total": 41.97}],
        "unknown": [], "subtotal": 41.97, "tax": 3.25, "total": 45.22,
    }}
    out = handle_message(repo, FakeProvider(raw, [priced]), "+9188", None,
                         "pickup")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["order_ready"] is True
    assert out["order_type"] == "pickup"
    assert out["order"]["items"][0]["unit_price"] == "13.99"
    assert out["order"]["total"] == "45.22"
    assert out["To_manager"] is False
    assert out["tools_called"] is True
    assert assistant.metadata["order_ready"] is True
    assert assistant.metadata["order"] == out["order"]
    assert assistant.metadata["tools_called"] is True
    assert assistant.metadata["response_fields"]["order_type"] == "pickup"


def test_current_call_name_reaches_verified_order_without_profile_write(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw(
        "Maya, your order is confirmed.", call_ended=True,
        order_ready=True, order_type="pickup", tools_called=True,
        name="Maya", order={"customer_name": "Maya"},
    )
    priced = {"name": "price_order", "result": {
        "items": [{"name": "Chilli Paneer", "price": 11.99,
                   "quantity": 1, "line_total": 11.99}],
        "unknown": [], "subtotal": 11.99, "tax": 0.93, "total": 12.92,
    }}
    out = handle_message(
        repo, FakeProvider(raw, [priced]), "+9199", None, "Maya"
    )
    assert out["name"] == "Maya"
    assert out["order"]["customer_name"] == "Maya"
    assert repo.get_user("+9199").name == ""  # shared phones stay unmodified


def test_verified_order_uses_no_name_sentinel_when_name_is_unavailable(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw(
        "Your order is confirmed.", call_ended=True, order_ready=True,
        order_type="pickup", tools_called=True, name="no_name_given",
    )
    priced = {"name": "price_order", "result": {
        "items": [{"name": "Samosa", "price": 2, "quantity": 1,
                   "line_total": 2}],
        "unknown": [], "subtotal": 2, "tax": 0.16, "total": 2.16,
    }}
    out = handle_message(repo, FakeProvider(raw, [priced]), "+9100", None, "no")
    assert out["order"]["customer_name"] == "no_name_given"


def test_manager_flag_is_returned_and_persisted(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Our manager will contact you.", call_ended=True,
               To_manager=True, order_type="catering", summary="Office catering",
               verbatim_user_chat=["I need catering"])
    out = handle_message(repo, FakeProvider(raw), "+9177", None, "catering")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["order_ready"] is False
    assert out["To_manager"] is True
    assert out["summary"] == "Office catering"
    assert out["order_type"] == "catering"
    assert assistant.metadata["To_manager"] is True
    assert assistant.metadata["response_fields"]["order_type"] == "catering"


def test_order_type_is_normalized_and_invalid_values_are_rejected():
    assert parse_model_response(_raw("Callback.", order_type="cake_and_catering"))["order_type"] == "cake/catering"
    assert parse_model_response(_raw("Delivery.", request_type="delivery"))["order_type"] == "delivery"
    assert parse_model_response(_raw("Unknown.", order_type="dine-in"))["order_type"] is None


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
    assert '"call_ended":true,"order_ready":true' in SYSTEM_PROMPT
    assert "yes, that is all, pickup in twenty minutes" in SYSTEM_PROMPT.lower()
    assert "[[END_CALL]]" not in SYSTEM_PROMPT


def test_prompt_allows_same_caller_to_request_detailed_order_history():
    from prompts import SYSTEM_PROMPT

    assert "do NOT refuse a request for \"my past orders\"" in SYSTEM_PROMPT
    assert "date or time, order name, items, quantities, total, order type" in SYSTEM_PROMPT
    assert "DETAILED HISTORY FOR THE SAME CALLER" in SYSTEM_PROMPT


def test_past_sessions_cannot_classify_the_current_order():
    from prompts import SYSTEM_PROMPT

    prompt = " ".join(SYSTEM_PROMPT.split())
    assert "historical reference only" in prompt
    assert "Never use its order type" in prompt
    assert "A past catering conversation never turns" in prompt
    assert "PAST CATERING DOES NOT CLASSIFY A NEW PARTY-SIZED REQUEST" in prompt
    assert "large combined quantity across" in prompt
    assert "keep order_type=null" in prompt
    assert "same event or separate requests" in prompt
    assert "remains caller speech even when it resembles an" in prompt


def test_cake_and_catering_callback_is_a_multi_turn_conversation():
    from prompts import SYSTEM_PROMPT

    assert "Cake orders are handled by my manager" in SYSTEM_PROMPT
    assert "Catering orders are handled by my manager" in SYSTEM_PROMPT
    assert "If you share the details with me" in SYSTEM_PROMPT
    assert "May I have the order details, please?" in SYSTEM_PROMPT
    assert "your requirements?" in SYSTEM_PROMPT
    assert "EVERY cake, catering, or combined inquiry" in SYSTEM_PROMPT
    assert "do not take cake orders" not in SYSTEM_PROMPT
    assert "do not take catering orders" not in SYSTEM_PROMPT
    assert "discussion for as many turns as needed" in SYSTEM_PROMPT
    assert "help them organize their thoughts" in SYSTEM_PROMPT
    assert "Do not disconnect or trigger the" in SYSTEM_PROMPT
    assert "Never claim that a specific" in SYSTEM_PROMPT
    assert "Never treat the caller's first description" in SYSTEM_PROMPT
    assert "answer that question before doing anything else" in SYSTEM_PROMPT
    assert "caller must explicitly indicate they are finished" in SYSTEM_PROMPT
    assert "requirements include a question; continue instead of handing off" in SYSTEM_PROMPT
    assert "What name should I include" in SYSTEM_PROMPT
    assert "most recent same-number order/callback context" in SYSTEM_PROMPT
    assert "do not ask for it again" in SYSTEM_PROMPT
    assert "Never choose an older" in SYSTEM_PROMPT
    assert "Aim for one or two useful" in SYSTEM_PROMPT
    assert "Do not repeat the same missing-detail question" in SYSTEM_PROMPT
    assert "unclear speech does not become an interrogation" in SYSTEM_PROMPT


def test_prompt_resolves_name_before_greeting_and_gates_ambiguous_handoffs():
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "NAME RESOLUTION PRECEDENCE — APPLY BEFORE THE FIRST REPLY" in prompt
    assert "A dated newer name overrides a conflicting older profile name" in prompt
    assert "Use the same resolved name consistently in the greeting" in prompt
    assert "CALLBACK-NAME GATE" in prompt
    assert "two or more different real names" in prompt
    assert "Do not set To_manager=true" in prompt
    assert "CONFLICTING FAMILY NAMES REQUIRE A CALLBACK NAME" in prompt
    assert "NEWER DATED NAME OVERRIDES A STALE PROFILE AT GREETING" in prompt


def test_model_cannot_mark_order_ready_without_actual_pricing_tool(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Order confirmed.", order_ready=True, tools_called=True)
    out = handle_message(repo, FakeProvider(raw), "+9188", None, "pickup")
    assert out["order_ready"] is False
    assert out["order"] is None
    assert out["tools_called"] is False
