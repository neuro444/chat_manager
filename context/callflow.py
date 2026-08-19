"""Structured model-response handling for call control."""
import json


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

    return {
        "answer": str(data.get("answer") or "").strip(),
        "call_ended": data.get("call_ended") is True,
        "order_placed": data.get("order_placed") is True,
        "To_manager": data.get("To_manager") is True,
        "tools_called": data.get("tools_called") is True,
        "summary": str(data.get("summary") or "").strip(),
        "verbatim_user_chat": (
            data.get("verbatim_user_chat")
            if isinstance(data.get("verbatim_user_chat"), list)
            else []
        ),
    }
