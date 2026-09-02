"""Structured model-response handling for call control."""
from context.response_model import CallResponse

_ORDER_TYPES = {"pickup", "cake", "catering", "cake/catering", "delivery"}


def parse_model_response(raw) -> dict:
    """Normalize a model response into the public chat-result contract.

    The OpenAI provider returns a schema-validated CallResponse, so there is no
    JSON text to parse here and no malformed case to recover from — Structured
    Outputs makes an invalid shape ungeneratable rather than merely unlikely.
    Dicts and plain strings are still accepted for test providers and for
    free-text callers such as the summarizer.
    """
    if isinstance(raw, CallResponse):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        # Free text is speech. It never carries control flags.
        data = {"answer": (raw or "").strip()}

    result = dict(data)
    raw_order_type = str(data.get("order_type") or "").strip().lower()
    if data.get("order_ready") is True:
        raw_order_type = "pickup"
    result.update({
        "answer": str(data.get("answer") or "").strip(),
        "call_ended": data.get("call_ended") is True,
        "order_ready": data.get("order_ready") is True,
        "order": data.get("order") if isinstance(data.get("order"), dict) else None,
        "To_manager": data.get("To_manager") is True,
        "Transfer_to_Manager": data.get("Transfer_to_Manager") is True,
        "tools_called": data.get("tools_called") is True,
        "order_type": raw_order_type if raw_order_type in _ORDER_TYPES else None,
        "summary": str(data.get("summary") or "").strip(),
        "verbatim_user_chat": (
            data.get("verbatim_user_chat")
            if isinstance(data.get("verbatim_user_chat"), list)
            else []
        ),
    })
    return result
