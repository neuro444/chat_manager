"""Dated recent-call context scoped to the same caller phone number."""
import config


def _session_facts(session, messages) -> list[str]:
    """Structured final-call facts saved on assistant-message metadata."""
    facts = []
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        metadata = message.metadata or {}
        extensions = metadata.get("response_fields") or {}
        order = metadata.get("order") or {}
        order_type = extensions.get("order_type")
        name = extensions.get("name") or order.get("customer_name")
        summary = metadata.get("summary")
        if order_type:
            facts.append(f"- order type: {order_type}")
        if name:
            facts.append(f"- order name: {name}")
        items = order.get("items") or []
        if items:
            rendered = ", ".join(
                f"{item.get('quantity', 1)} × {item.get('name', '')}" for item in items
            )
            facts.append(f"- ordered items: {rendered}")
        if order.get("total"):
            facts.append(f"- order total: {order['total']}")
        if summary:
            facts.append(f"- call summary: {summary}")
        if facts:
            break
    if session.running_summary:
        facts.append(f"- conversation summary: {session.running_summary}")
    return facts

def build_memory_context(
    repo, user_id: str, query: str, current_session: str, entities: list[str] | None = None
) -> str:
    """Return the latest dated messages from this phone number's prior calls.

    `user_id` is the caller phone number at the API boundary. We intentionally
    retain both caller and assistant turns: an order name such as "Sri Krishna"
    only has meaning beside the assistant's preceding name question. Different
    family members may share a phone, so this is conversation context rather
    than a permanent person-name profile.
    """
    sessions = []
    for session in repo.list_sessions(user_id, 50):
        if session.session_id == current_session:
            continue
        messages = [
            message for message in repo.all_messages(session.session_id)
            if message.role in {"user", "assistant"}
        ]
        if not messages:
            continue
        sessions.append((session, messages))
        if len(sessions) >= config.CROSS_SESSION_SESSION_WINDOW:
            break

    if not sessions:
        return ""

    # Divide the transcript allowance across calls so one long conversation
    # cannot hide the other recent sessions. Structured facts are always kept.
    base, extra = divmod(config.CROSS_SESSION_MESSAGE_WINDOW, len(sessions))
    calls = []
    for index, (session, messages) in enumerate(sessions):
        quota = base + (1 if index < extra else 0)
        transcript = messages[-quota:] if quota else []
        stamp = session.updated_at.strftime("%Y-%m-%d %H:%M UTC")
        status = "completed" if session.metadata.get("ended") else "open"
        lines = [f"Previous call — {stamp} — {status}"]
        lines.extend(_session_facts(session, messages))
        lines.append("- transcript:")
        for message in transcript:
            role = "caller" if message.role == "user" else "assistant"
            content = message.content.strip().replace("\n", " ")[:500]
            lines.append(f"  - {role}: {content}")
        calls.append("\n".join(lines))
    return "\n\n".join(calls)
