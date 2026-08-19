"""Recent-turn window — layer 3 of the context stack."""
from models import Message


def get_history(repo, session_id: str, limit: int, exclude_last: bool = True) -> list[dict]:
    """Return recent turns as {role, content} dicts, oldest first.

    `exclude_last` drops the message just written for this turn, so the
    assembler can append it once rather than sending it twice.
    """
    msgs: list[Message] = repo.recent_messages(session_id, limit + 1)
    if exclude_last and msgs:
        msgs = msgs[:-1]
    return [{"role": m.role, "content": m.content} for m in msgs][-limit:]
