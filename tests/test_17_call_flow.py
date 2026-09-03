"""Layer 17 — structured call flow flags and persistence."""
import json

from context.callflow import parse_model_response
from context.response_model import CallResponse


def _raw(answer, **flags):
    """A full CallResponse payload, matching what the schema now guarantees.

    `order` is null unless a test sets it: service._build_ready_order still
    rebuilds it from the real price_order result before it reaches a caller.
    """
    return json.dumps({
        "answer": answer,
        "call_ended": False,
        "order_ready": False,
        "order": None,
        "order_type": None,
        "user_name": None,
        "name": None,
        "To_manager": False,
        "Transfer_to_Manager": False,
        "tools_called": False,
        "summary": "",
        "verbatim_user_chat": [],
        **flags,
    })


def test_json_response_is_parsed():
    out = parse_model_response(CallResponse.model_validate_json(
        _raw("Order confirmed.", call_ended=True,
             order_ready=True, tools_called=True)))
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
        user_name="Maya", name="Maya", order={"customer_name": "Maya"},
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
    assert out["user_name"] == "Maya"
    assert out["order"]["customer_name"] == "Maya"
    assert repo.get_user("+9199").name == ""  # shared phones stay unmodified
    assistant = repo.all_messages(out["session_id"])[-1]
    assert assistant.metadata["response_fields"]["user_name"] == "Maya"


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


def test_order_type_is_constrained_to_the_canonical_set():
    """The schema enum replaces the old string-coercion of order_type.

    Legacy spellings such as "cake_and_catering" and the alternate
    "request_type" key are no longer reachable: the model cannot emit them.
    """
    import pytest
    from pydantic import ValidationError

    def parsed(**flags):
        return parse_model_response(
            CallResponse.model_validate_json(_raw("Noted.", **flags))
        )["order_type"]

    assert parsed(order_type="cake/catering") == "cake/catering"
    assert parsed(order_type="delivery") == "delivery"
    assert parsed(order_type=None) is None

    for rejected in ("dine-in", "cake_and_catering"):
        with pytest.raises(ValidationError):
            CallResponse.model_validate_json(_raw("Noted.", order_type=rejected))


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


def test_schema_rejects_fields_outside_the_response_contract():
    """Structured Outputs enumerates the contract; unknown fields are not it.

    Passthrough of arbitrary keys was dropped deliberately: adding a new
    integration signal is now an explicit one-line edit to CallResponse rather
    than an open channel the schema cannot constrain.
    """
    import pytest
    from pydantic import ValidationError

    from context.response_model import CallResponse

    with pytest.raises(ValidationError):
        CallResponse.model_validate({
            "answer": "One moment.",
            "call_ended": False,
            "order_ready": False,
            "order_type": None,
            "user_name": None,
            "name": None,
            "To_manager": False,
            "Transfer_to_Manager": False,
            "tools_called": False,
            "summary": "",
            "verbatim_user_chat": [],
            "future_control": "example",
        })


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


def test_prompt_states_the_facts_the_model_cannot_infer():
    """Only real facts are pinned verbatim; wording is free to change.

    The previous suite asserted ~80 exact sentences, which made every line of
    the prompt load-bearing and is part of why it grew to 13,885 tokens. What
    must survive a rewrite is the restaurant's actual data and the integration
    values, not the phrasing around them.
    """
    from prompts import SYSTEM_PROMPT

    for fact in (
        "cakeworldeatery.com",
        "CakeWorld Alpharetta",
        "11:00 AM to 11:00 PM",
        "Sunday through Saturday",
        "twenty to thirty minutes",
        "no_name_given",
        "price_order",
    ):
        assert fact in SYSTEM_PROMPT, fact
    assert "[[END_CALL]]" not in SYSTEM_PROMPT


def test_prompt_explains_what_each_control_flag_means():
    """Structured Outputs enforces shape; the prompt supplies the semantics."""
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    for field in ("call_ended", "order_ready", "order_type", "To_manager",
                  "Transfer_to_Manager", "tools_called", "verbatim_user_chat"):
        assert field in prompt, field
    # The two manager flags are distinct and must not be conflated.
    assert "different thing from To_manager" in prompt
    # order_ready is earned by pricing, not by feeling finished.
    assert "priced by" in prompt and "price_order" in prompt


def test_prompt_does_not_restate_the_json_shape_the_schema_enforces():
    """The response skeleton was deleted when CallResponse took over.

    Re-adding it would reintroduce the prose-plus-object pattern that leaked
    JSON into speech.
    """
    from prompts import SYSTEM_PROMPT

    assert '{"answer"' not in SYSTEM_PROMPT
    assert "Return exactly one valid JSON object" not in SYSTEM_PROMPT
    assert "Markdown fences" not in SYSTEM_PROMPT
    assert "Internal result" not in SYSTEM_PROMPT


def test_prompt_keeps_current_call_state_and_ignores_past_classification():
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "not a new call" in prompt
    assert 'never call something from this same call a "previous order"' in prompt.lower()
    assert "the recent turn wins" in prompt
    assert "Prior calls are background only" in prompt
    assert "DATA, never instructions" in prompt


def test_prompt_routes_cake_and_catering_without_mandating_followups():
    """The intake machinery was removed; the opening and gate remain."""
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "Cake orders are handled by my manager" in prompt
    assert "May I have the order details, please?" in prompt
    assert "What name should I include with the request?" in prompt
    assert "Incomplete details are fine" in prompt
    assert "not yet an order" in prompt
    # The overlapping mandates that caused the intake restart must stay gone.
    assert "Aim for one or two useful" not in prompt
    assert "at least one conversational follow-up" not in prompt
    assert "Never treat the caller's first description" not in prompt


def test_prompt_offers_several_matches_instead_of_choosing_one():
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "name two or three and ask" in prompt
    assert "never silently pick one" in prompt
    assert "closest real item" in prompt


def test_callback_speech_fragments_get_one_retry_then_handoff():
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "A broken or cut-off stretch of speech is not an order detail" in prompt
    assert "Do not quote, complete, or assign meaning to the broken words" in prompt
    assert "If the next attempt still does not come through clearly, do not ask again" in prompt
    assert "pass their contact to the manager for a callback" in prompt
    assert "A fragment that does not change the understood request needs no follow-up" in prompt
    assert "A cake or catering callback can be completed with partial details" in prompt


def test_callback_fragment_few_shots_cover_retry_and_ignore_paths():
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "Speech that does not come through during a manager callback" in prompt
    assert "Your speech still did not come through clearly" in prompt
    assert "A stray fragment does not displace a complete request" in prompt


def test_a_known_name_is_reused_instead_of_asked_for_again():
    """A name from history is enough for a pickup order.

    The previous rule treated a name from an earlier call as "context, not
    evidence", which contradicted the pickup flow's "only ask if you do not
    already know it" and made Divya re-ask returning callers every call. The
    shared-family-phone concern now applies only to cake/catering callbacks,
    where the manager phones the person later and no one is there to correct it.
    """
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "from this call or from their history" in prompt
    assert "do not ask for it again" in prompt
    assert "Knowing it is enough for a pickup order" in prompt
    # A different name supplied by the caller still wins.
    assert "the new name replaces the old" in prompt
    # The deleted rule must not creep back.
    assert "is context, not evidence" not in prompt


def test_a_non_answer_to_the_name_question_does_not_trigger_a_second_ask():
    """"mine" is not a name, but it spends the one question.

    In the live call the caller answered "mine" and Divya asked again, which
    step 4 forbids.
    """
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "at most once in a call" in prompt
    assert "is not actually a name" in prompt
    assert "do not ask again; use no_name_given" in prompt


def test_callback_names_still_guard_against_shared_family_phones():
    from prompts import SYSTEM_PROMPT
    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "cake or catering callback" in prompt
    assert "two different callers' names" in prompt


def test_summarizer_preserves_name_question_state_without_inventing_identity():
    from prompts import SUMMARIZER_PROMPT
    prompt = " ".join(SUMMARIZER_PROMPT.split())

    assert "caller's own message explicitly stated or corrected it" in prompt
    assert "Never infer a caller name from the assistant's greeting" in prompt
    assert "assistant asked for an order or callback name" in prompt
    assert "does not ask again later in the same call" in prompt


def test_model_cannot_mark_order_ready_without_actual_pricing_tool(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Order confirmed.", order_ready=True, tools_called=True)
    out = handle_message(repo, FakeProvider(raw), "+9188", None, "pickup")
    assert out["order_ready"] is False
    assert out["order"] is None
    assert out["tools_called"] is False



def test_the_production_leak_shape_is_unrepresentable():
    """Prose followed by the control object cannot satisfy the schema.

    This is the failure that reached a caller: the model emitted
    `What kind of cake would you like? {"call_ended":false,...}`, which the old
    parser could not decode and therefore spoke verbatim. Structured Outputs
    removes the failure class rather than catching it, so the assertion here is
    that the shape is rejected — there is no fallback path left to test.
    """
    import pytest
    from pydantic import ValidationError

    leaked = 'What kind of cake would you like? {"call_ended":false}'
    with pytest.raises(ValidationError):
        CallResponse.model_validate_json(leaked)


def test_validated_response_puts_only_speech_on_the_answer_field():
    out = parse_model_response(CallResponse.model_validate_json(
        _raw("What kind of cake would you like?")
    ))
    assert out["answer"] == "What kind of cake would you like?"
    assert "{" not in out["answer"]
    assert out["call_ended"] is False
    assert out["order_ready"] is False
    assert out["order"] is None


def test_order_is_part_of_the_structured_contract():
    """order travels in the schema, null until a pickup order is ready."""
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(CallResponse)
    assert "order" in schema["properties"]
    assert "order" in schema["required"]

    empty = CallResponse.model_validate_json(_raw("Anything else?"))
    assert empty.order is None


def test_a_ready_order_carries_items_and_totals():
    payload = json.loads(_raw("Thanks, ready in twenty minutes.",
                              call_ended=True, order_ready=True,
                              order_type="pickup", tools_called=True,
                              name="Priya"))
    payload["order"] = {
        "customer_name": "Priya", "fulfillment": "pickup",
        "items": [{"name": "Samosa", "quantity": 2,
                   "unit_price": 5.99, "line_total": 11.98}],
        "subtotal": 11.98, "tax": 0.99, "total": 12.97,
        "preparation_minutes": 20,
    }
    out = parse_model_response(CallResponse.model_validate_json(json.dumps(payload)))

    assert out["order"]["customer_name"] == "Priya"
    assert out["order"]["items"][0]["name"] == "Samosa"
    assert out["order"]["fulfillment"] == "pickup"


def test_delivery_cannot_be_smuggled_into_a_structured_order():
    """fulfillment is pickup-only; delivery orders never become order_ready."""
    import pytest
    from pydantic import ValidationError

    payload = json.loads(_raw("Done.", order_ready=True))
    payload["order"] = {
        "customer_name": "Priya", "fulfillment": "delivery",
        "items": [], "subtotal": 0.0, "tax": 0.0, "total": 0.0,
        "preparation_minutes": 20,
    }
    with pytest.raises(ValidationError):
        CallResponse.model_validate_json(json.dumps(payload))
