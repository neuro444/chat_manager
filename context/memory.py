"""Dated recent-call context scoped to the same caller phone number."""
import config

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
    remaining = config.CROSS_SESSION_MESSAGE_WINDOW
    calls = []
    for session in repo.list_sessions(user_id, 50):
        if session.session_id == current_session or remaining <= 0:
            continue
        messages = [
            message for message in repo.all_messages(session.session_id)
            if message.role in {"user", "assistant"}
        ]
        if not messages:
            continue
        messages = messages[-remaining:]
        remaining -= len(messages)
        stamp = session.updated_at.strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"Previous call — {stamp}"]
        for message in messages:
            role = "caller" if message.role == "user" else "assistant"
            content = message.content.strip().replace("\n", " ")[:500]
            lines.append(f"- {role}: {content}")
        calls.append("\n".join(lines))
    return "\n\n".join(calls)
