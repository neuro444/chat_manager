"""Structured model-response handling for call control."""
import json


_ORDER_TYPES = {"pickup", "cake", "catering", "cake/catering", "delivery"}


def parse_model_response(raw: str | dict) -> dict:
    """Normalize an LLM response into the public chat-result contract."""
    if isinstance(raw, dict):
        data = dict(raw)
    else:
        text = (raw or "").strip()
        if text.startswith("```json"):
            text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        try:
            parsed = json.loads(text)
            data = parsed if isinstance(parsed, dict) else {"answer": text}
        except (json.JSONDecodeError, TypeError):
            # Safe fallback: speak the text, but never infer action flags from it.
            data = {"answer": text}

    # Preserve additional JSON fields introduced by the prompt so adding a new
    # integration signal does not require rebuilding this parser. Established
    # control fields are still normalized below instead of trusting truthy
    # strings or malformed values from the model.
    result = dict(data)
    raw_order_type = str(
        data.get("order_type") or data.get("request_type") or ""
    ).strip().lower()
    # Accept the legacy prompt spelling, but expose one canonical value.
    if raw_order_type == "cake_and_catering":
        raw_order_type = "cake/catering"
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
