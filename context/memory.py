"""Cross-session memory — retrieval over the user's OTHER sessions."""
import config

_HISTORY_CUES = (
    "last time", "previous", "before", "usual", "again", "same as",
    "what did i", "my last", "earlier", "recent",
)


def _looks_like_history_question(text: str) -> bool:
    low = (text or "").lower()
    return any(cue in low for cue in _HISTORY_CUES)


def _last_call_messages(repo, user_id, current_session, limit=6):
    """The caller's user-messages from their most recent other session."""
    for sess in repo.list_sessions(user_id, 5):
        if sess.session_id == current_session:
            continue
        msgs = [m for m in repo.all_messages(sess.session_id) if m.role == "user"]
        if msgs:
            return msgs[-limit:]
    return []


def build_memory_context(
    repo, user_id: str, query: str, current_session: str, entities: list[str] | None = None
) -> str:
    """Return a text block of relevant past-conversation snippets, or ''.

    Always scoped to user_id — this is the boundary that keeps one user's
    history out of another user's prompt.
    """
    search_text = query
    if entities:
        search_text = f"{query} {' '.join(entities)}"

    hits = repo.search_messages(
        user_id, search_text, current_session, config.CROSS_SESSION_WINDOW
    )

    # A vague follow-up ("what did I order last time?") shares no keywords with
    # the order itself. Fall back to the caller's most recent previous call.
    if not hits and _looks_like_history_question(query):
        hits = _last_call_messages(repo, user_id, current_session)

    if not hits:
        return ""

    lines = []
    for h in hits:
        snippet = h.content.strip().replace("\n", " ")[:200]
        lines.append(f"- {snippet}")
    return "\n".join(lines)
