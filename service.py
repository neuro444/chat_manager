"""Orchestrator — the single public entry point for a chat turn.

The CLI and the HTTP API both call handle_message() and nothing else. If
anything outside this module needs to import from context/ or storage/, a
boundary has leaked.
"""
from datetime import datetime, timedelta, timezone
from time import perf_counter
import json

import config
from context.assembler import assemble
from context.caller import capture_name
from context.callflow import parse_model_response
from context.history import get_history
from context.memory import build_memory_context
from context.state import resolve_active_entities
from context.summary import maybe_roll_summary
from menu.loader import format_menu_for_prompt


def _debug(msg: str) -> None:
    """Print transcript-bearing debug output only when DEBUG_CONTEXT is on.

    Call content is PII (user_id is the caller's phone number), so these lines
    must stay out of container logs on the server. Timing lines are not gated —
    they carry no message content and are useful in production.
    """
    if config.DEBUG_CONTEXT:
        print(msg, flush=True)


def build_context(repo, user_id: str, session_id: str, user_message: str) -> list[dict]:
    """Assemble the full prompt for a turn. Exposed so /context can inspect it."""
    session = repo.get_session(session_id)
    entities = resolve_active_entities(repo, session_id, user_message)

    history = get_history(repo, session_id, config.HISTORY_WINDOW)
    summary = session.running_summary if session else ""
    # Past conversations are available as preference context. The system prompt
    # controls how they may be referenced; they are never database mutations.
    memory = build_memory_context(repo, user_id, user_message, session_id, entities)

    user = repo.get_user(user_id)
    bits = [f"Caller phone: {user_id}"]
    if user and user.name:
        # Whether to say the name is turn-dependent: greeting or final
        # confirmation only. Telling the model on every turn to "greet them by
        # name" is what makes it repeat the name in every reply.
        first_turn = repo.message_count(session_id) <= 1
        when = ("greet them by name now" if first_turn
                else "do NOT use their name in this reply unless you are "
                     "confirming the final order")
        bits.append(f"Caller name: {user.name} ({when})")
    profile = "\n".join(bits)

    return assemble(
        user_message=user_message,
        history=history,
        summary=summary,
        memory=memory,
        profile=profile,
        domain=format_menu_for_prompt(),
    )


def _is_expired(session) -> bool:
    """A call that has been silent past the timeout is over."""
    updated = session.updated_at
    if isinstance(updated, str):
        updated = datetime.fromisoformat(updated)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - updated
    return age > timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)


def resolve_session(repo, user_id: str, session_id: str | None) -> str:
    """Reuse the caller's live session, or open a new one.

    A new phone call must not land inside the previous call's transcript, so a
    session that has been idle past SESSION_TIMEOUT_MINUTES is left closed.
    """
    if session_id and repo.get_session(session_id) is not None:
        return session_id
    if session_id is None:
        recent = repo.list_sessions(user_id, 1)
        if (recent and not _is_expired(recent[0])
                and not recent[0].metadata.get("ended")):
            return recent[0].session_id
    return repo.create_session(user_id).session_id


def _start_turn(repo, user_id, session_id, user_message):
    """Shared prologue: resolve session, persist the user turn, build context."""
    repo.ensure_user(user_id)
    session_id = resolve_session(repo, user_id, session_id)
    is_first_turn = repo.message_count(session_id) == 0
    capture_name(repo, user_id, user_message)

    # persist the user turn BEFORE calling the LLM, so a failure mid-call never
    # loses what the user typed
    repo.append_message(session_id, "user", user_message)
    messages = build_context(repo, user_id, session_id, user_message)
    if config.DEBUG_CONTEXT:
        from context.debug import print_context_report
        print_context_report(repo, user_id, session_id, user_message)
    return session_id, is_first_turn, messages


def _complete(provider, messages):
    """Call the provider, offering the ordering tools when it supports them."""
    from orders.tools import TOOL_SCHEMAS
    try:
        return provider.complete(messages, tools=TOOL_SCHEMAS)
    except TypeError:
        return provider.complete(messages)      # providers without tool support


def _finish_turn(
    repo, provider, session_id, user_message, answer, is_first_turn,
    llm_latency_ms, order_ready=False, order=None, to_manager=False,
    tools_called=False, summary="", verbatim_user_chat=None,
    response_fields=None,
):
    """Shared epilogue: persist the reply, then post-turn work."""
    repo.append_message(
        session_id,
        "assistant",
        answer,
        metadata={
            "model": config.LLM_MODEL,
            "llm_latency_ms": llm_latency_ms,
            "order_ready": order_ready,
            "order": order,
            "To_manager": to_manager,
            "tools_called": tools_called,
            "summary": summary,
            "verbatim_user_chat": verbatim_user_chat or [],
            "response_fields": response_fields or {},
        },
    )
    if is_first_turn:
        repo.rename_session(session_id, user_message[:50])
    maybe_roll_summary(repo, provider, session_id)


_PUBLIC_CORE_FIELDS = {
    "answer", "session_id", "call_ended", "order_ready", "order",
    "To_manager", "tools_called", "summary", "verbatim_user_chat",
    "end_delay_seconds",
}


def _response_extensions(parsed: dict) -> dict:
    """Pass prompt-defined integration fields through without bespoke wiring."""
    return {key: value for key, value in parsed.items()
            if key not in _PUBLIC_CORE_FIELDS}


def _money(value) -> str:
    """Serialize money consistently for downstream order systems."""
    return f"{float(value):.2f}"


def _build_ready_order(repo, provider, user_id: str, requested: bool):
    """Build an order only from an actual successful price_order tool result.

    The LLM controls conversation wording, but it is not the source of truth for
    item names or money. The external integration may submit this object later.
    """
    if not requested:
        return False, None

    priced = None
    for invocation in reversed(getattr(provider, "last_tool_results", [])):
        if invocation.get("name") == "price_order":
            priced = invocation.get("result")
            break
    if isinstance(priced, str):
        try:
            priced = json.loads(priced)
        except json.JSONDecodeError:
            priced = None
    if not isinstance(priced, dict) or priced.get("unknown"):
        return False, None
    lines = priced.get("items")
    if not isinstance(lines, list) or not lines:
        return False, None

    items = []
    try:
        for line in lines:
            quantity = int(line["quantity"])
            if quantity <= 0:
                return False, None
            items.append({
                "name": str(line["name"]),
                "quantity": quantity,
                "unit_price": _money(line["price"]),
                "line_total": _money(line["line_total"]),
            })
        subtotal = _money(priced["subtotal"])
        tax = _money(priced["tax"])
        total = _money(priced["total"])
    except (KeyError, TypeError, ValueError):
        return False, None

    user = repo.get_user(user_id)
    return True, {
        "customer_name": user.name if user else "",
        "fulfillment": "pickup",
        "items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "preparation_minutes": config.PICKUP_PREPARATION_MINUTES,
    }


def handle_message(repo, provider, user_id, session_id, user_message):
    """Run one full turn and return {"answer", "session_id"}."""
    session_id, is_first, messages = _start_turn(
        repo, user_id, session_id, user_message
    )
    print(f"[llm_call_start] session_id={session_id}", flush=True)
    llm_started = perf_counter()
    raw = _complete(provider, messages)
    llm_latency_ms = round((perf_counter() - llm_started) * 1000, 2)
    _debug(f"[llm_raw_response] session_id={session_id} response={raw!r}")
    print(
        f"[llm_call_complete] session_id={session_id} "
        f"response_time_ms={llm_latency_ms} "
        f"response_time_seconds={llm_latency_ms / 1000:.2f}",
        flush=True,
    )
    parsed = parse_model_response(raw)
    parsed["tools_called"] = bool(
        getattr(provider, "last_tools_called", parsed["tools_called"])
    )
    ended = parsed["call_ended"]
    order_ready, order = _build_ready_order(
        repo, provider, user_id, parsed["order_ready"]
    )
    to_manager = parsed["To_manager"]
    extensions = _response_extensions(parsed)
    answer = parsed["answer"]
    _finish_turn(
        repo, provider, session_id, user_message, answer, is_first,
        llm_latency_ms, order_ready, order, to_manager, parsed["tools_called"],
        parsed["summary"], parsed["verbatim_user_chat"],
        extensions,
    )
    if ended:
        repo.mark_session_ended(session_id)
    result = {
        **extensions,
        "answer": answer,
        "session_id": session_id,
        "call_ended": ended,
        "order_ready": order_ready,
        "order": order,
        "To_manager": to_manager,
        "tools_called": parsed["tools_called"],
        "summary": parsed["summary"],
        "verbatim_user_chat": parsed["verbatim_user_chat"],
        "end_delay_seconds": config.CALL_END_DELAY_SECONDS if ended else 0,
    }
    _debug(f"[chat_result] {json.dumps(result, ensure_ascii=False)}")
    return result


def stream_message(repo, provider, user_id, session_id, user_message):
    """Same turn, streamed. Yields text deltas, then a final dict.

    Kept separate from handle_message because a function containing `yield`
    is a generator even on the non-streaming path.
    """
    session_id, is_first, messages = _start_turn(
        repo, user_id, session_id, user_message
    )
    chunks = []
    print(f"[llm_call_start] session_id={session_id} stream=true", flush=True)
    llm_started = perf_counter()
    for delta in provider.stream(messages):
        chunks.append(delta)
        yield delta
    llm_latency_ms = round((perf_counter() - llm_started) * 1000, 2)
    print(
        f"[llm_call_complete] session_id={session_id} stream=true "
        f"response_time_ms={llm_latency_ms} "
        f"response_time_seconds={llm_latency_ms / 1000:.2f}",
        flush=True,
    )
    raw = "".join(chunks)
    _debug(f"[llm_raw_response] session_id={session_id} response={raw!r}")
    parsed = parse_model_response(raw)
    parsed["tools_called"] = bool(
        getattr(provider, "last_tools_called", parsed["tools_called"])
    )
    ended = parsed["call_ended"]
    order_ready, order = _build_ready_order(
        repo, provider, user_id, parsed["order_ready"]
    )
    to_manager = parsed["To_manager"]
    extensions = _response_extensions(parsed)
    answer = parsed["answer"]
    _finish_turn(
        repo, provider, session_id, user_message, answer, is_first,
        llm_latency_ms, order_ready, order, to_manager, parsed["tools_called"],
        parsed["summary"], parsed["verbatim_user_chat"],
        extensions,
    )
    if ended:
        repo.mark_session_ended(session_id)
    return {
        **extensions,
        "answer": answer,
        "session_id": session_id,
        "call_ended": ended,
        "order_ready": order_ready,
        "order": order,
        "To_manager": to_manager,
        "tools_called": parsed["tools_called"],
        "summary": parsed["summary"],
        "verbatim_user_chat": parsed["verbatim_user_chat"],
        "end_delay_seconds": config.CALL_END_DELAY_SECONDS if ended else 0,
    }
