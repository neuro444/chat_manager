"""Layer 17 — structured call flow flags and persistence."""
import json

from context.callflow import parse_model_response


def _raw(answer, **flags):
    return json.dumps({
        "answer": answer,
        "call_ended": False,
        "order_placed": False,
        "To_manager": False,
        "tools_called": False,
        "summary": "",
        "verbatim_user_chat": [],
        **flags,
    })


def test_json_response_is_parsed():
    out = parse_model_response(_raw("Order confirmed.", call_ended=True,
                                    order_placed=True, tools_called=True))
    assert out["answer"] == "Order confirmed."
    assert out["call_ended"] is True
    assert out["order_placed"] is True
    assert out["tools_called"] is True


def test_plain_text_fallback_never_infers_action_flags():
    out = parse_model_response("still ordering")
    assert out["answer"] == "still ordering"
    assert out["call_ended"] is False
    assert out["order_placed"] is False
    assert out["To_manager"] is False


def test_order_flags_are_returned_and_persisted(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Order confirmed. CakeWorld Alpharetta.", call_ended=True,
               order_placed=True, tools_called=True)
    out = handle_message(repo, FakeProvider(raw), "+9188", None, "pickup")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["order_placed"] is True
    assert out["To_manager"] is False
    assert out["tools_called"] is True
    assert assistant.metadata["order_placed"] is True
    assert assistant.metadata["tools_called"] is True


def test_manager_flag_is_returned_and_persisted(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message

    raw = _raw("Our manager will contact you.", call_ended=True,
               To_manager=True, summary="Office catering",
               verbatim_user_chat=["I need catering"])
    out = handle_message(repo, FakeProvider(raw), "+9177", None, "catering")
    assistant = repo.all_messages(out["session_id"])[-1]
    assert out["order_placed"] is False
    assert out["To_manager"] is True
    assert out["summary"] == "Office catering"
    assert assistant.metadata["To_manager"] is True


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
    assert "order_placed" in SYSTEM_PROMPT
    assert "tools_called" in SYSTEM_PROMPT
    assert "[[END_CALL]]" not in SYSTEM_PROMPT
