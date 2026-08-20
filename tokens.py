"""Token accounting for LLM calls.

Two sources, deliberately kept distinct:

- **tiktoken** counts the exact text we send and receive, locally, before and
  after the call. Always available, costs nothing, and works for any provider.
- **The API's own usage object** is what OpenAI actually billed. It is the
  authority when present, and it differs from the local count for reasons the
  local count cannot see: tool-call round trips inside one turn, reasoning
  tokens, and server-side prompt handling.

We report the API's numbers when we have them and fall back to the local
estimate when we do not, with `token_source` naming which one you are reading.
Conflating the two produces numbers that silently disagree with the invoice.
"""
import logging

import config

logger = logging.getLogger(__name__)

_encoder = None
_encoder_failed = False

# Chat models serialize each message with a few tokens of role/delimiter
# scaffolding. 4 per message + 3 to prime the reply is OpenAI's documented
# approximation and is close enough for a budget estimate.
_TOKENS_PER_MESSAGE = 4
_REPLY_PRIMING_TOKENS = 3


def _get_encoder():
    """Load tiktoken lazily; degrade to the character heuristic if unavailable.

    Token counting must never be the reason a call fails, so every failure
    here is logged once and swallowed.
    """
    global _encoder, _encoder_failed
    if _encoder is not None or _encoder_failed:
        return _encoder
    try:
        import tiktoken

        try:
            _encoder = tiktoken.encoding_for_model(config.LLM_MODEL)
        except KeyError:
            # Unknown/new model names fall back to the current encoding
            # rather than failing — o200k_base covers the GPT-4o+ family.
            _encoder = tiktoken.get_encoding(config.TIKTOKEN_ENCODING)
    except Exception:
        _encoder_failed = True
        logger.warning(
            "tiktoken unavailable; falling back to a character-based estimate",
            exc_info=True,
        )
    return _encoder


def count_text(text: str) -> int:
    """Token count for one string."""
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is None:
        return len(text) // config.CHARS_PER_TOKEN
    return len(encoder.encode(text))


def count_messages(messages: list[dict]) -> int:
    """Token count for an assembled request, including per-message overhead.

    Handles the tool items the Responses API mixes into the same list
    (function_call / function_call_output carry no "content").
    """
    total = 0
    for message in messages or []:
        total += _TOKENS_PER_MESSAGE
        for key in ("content", "arguments", "output", "name"):
            value = message.get(key)
            if isinstance(value, str):
                total += count_text(value)
    return total + _REPLY_PRIMING_TOKENS


def usage_from_response(response) -> dict | None:
    """Extract the API's own token usage, if the provider exposed it.

    Returns None when the provider does not report usage (e.g. the fake
    provider in tests, or a streamed call), so callers can fall back.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if input_tokens is None or output_tokens is None:
        return None
    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(
            getattr(usage, "total_tokens", input_tokens + output_tokens)
        ),
    }


def session_history(repo, session_id: str) -> dict:
    """Per-turn latency and TTS characters for every turn so far this call.

    Read back from the assistant messages already persisted, so the lists
    survive a restart and cost nothing extra to maintain. Index 0 is the
    first turn of the call.
    """
    latencies: list[float] = []
    tts_chars: list[int] = []
    try:
        messages = repo.all_messages(session_id)
    except Exception:  # never let telemetry break a live call
        logger.warning("could not read session history for %s", session_id,
                       exc_info=True)
        return {"latency_ms_per_turn": [], "tts_chars_per_turn": []}

    for message in messages:
        if message.role != "assistant":
            continue
        meta = message.metadata or {}
        latency = meta.get("llm_latency_ms")
        if latency is not None:
            latencies.append(latency)
        tts_chars.append(meta.get("tts_chars", 0))
    return {"latency_ms_per_turn": latencies, "tts_chars_per_turn": tts_chars}


def count_tts_chars(answer: str) -> int:
    """Characters ElevenLabs is billed for on this turn.

    Only `answer` is ever spoken — the JSON envelope, flags, and summary are
    never sent to TTS, so counting the raw model output would overstate the
    bill substantially.
    """
    return len(answer or "")


def report(messages, raw, provider, model: str) -> dict:
    """Build the token block that goes on the /chat response.

    Prefers the provider's reported usage (what you are billed for) and falls
    back to the local tiktoken count. `token_source` says which you got.
    """
    reported = getattr(provider, "last_usage", None)
    estimated_input = count_messages(messages)
    estimated_output = count_text(raw or "")

    if reported:
        return {
            "model_used": model,
            "input_tokens": reported["input_tokens"],
            "output_tokens": reported["output_tokens"],
            "total_tokens": reported["total_tokens"],
            "token_source": "api",
            # The local count ignores tool round trips, so a gap here is
            # expected on tool-using turns rather than a bug.
            "estimated_input_tokens": estimated_input,
            "estimated_output_tokens": estimated_output,
        }

    return {
        "model_used": model,
        "input_tokens": estimated_input,
        "output_tokens": estimated_output,
        "total_tokens": estimated_input + estimated_output,
        "token_source": "tiktoken" if _get_encoder() else "estimate",
    }
