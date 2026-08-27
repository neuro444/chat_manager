"""Developer-facing context report.

Prints the five contexts that feed a turn. The menu is abbreviated here for
readability — the model always receives it in full via context/assembler.py.
"""
import config
from context.memory import build_memory_context
from context.state import resolve_active_entities
from menu.loader import format_menu_for_prompt

PAST_SESSION_LIMIT = 20
_RULE = "─" * 72


def abbreviate(text: str, words: int = 100) -> str:
    """Keep the first and last words verbatim, elide the middle."""
    parts = (text or "").split()
    if len(parts) <= words:
        return text or ""
    head = " ".join(parts[: words // 2])
    tail = " ".join(parts[-(words // 2):])
    hidden = len(parts) - words
    return f"{head}\n   ...[{hidden} words hidden — model receives all of it]...\n{tail}"


def _section(num: int, title: str, body: str, note: str = "") -> str:
    body = (body or "").rstrip() or "(empty)"
    header = f"{num}. {title}"
    if note:
        header += f"  [{note}]"
    return f"{_RULE}\n{header}\n{_RULE}\n{body}\n"


def build_context_report(repo, user_id: str, session_id: str, user_message: str) -> str:
    """Render the five contexts as text."""
    session = repo.get_session(session_id)
    entities = resolve_active_entities(repo, session_id, user_message)
    out = [f"\n{'═' * 72}\nCONTEXT FOR TURN — caller {user_id}"
           f" · session {session_id[:8]}\n{'═' * 72}"]

    # 1 — the current query
    note = f"entities: {', '.join(entities)}" if entities else "no entities"
    out.append(_section(1, "USER QUERY", user_message, note))

    # 2 — this session's recent turns
    recent = repo.recent_messages(session_id, config.HISTORY_WINDOW)
    lines = [f"[{m.seq}] {m.role}: {m.content}" for m in recent]
    out.append(_section(2, "CHAT SESSION HISTORY", "\n".join(lines),
                        f"last {config.HISTORY_WINDOW} turns of this call"))

    # 3 — retrieval hits from this caller's other sessions
    memory = build_memory_context(repo, user_id, user_message, session_id, entities)
    out.append(_section(3, "RECENT SESSIONS (same caller)", memory,
                        f"top {config.CROSS_SESSION_WINDOW} matches"))

    # 4 — every past call, summarized
    past = [s for s in repo.list_sessions(user_id, PAST_SESSION_LIMIT + 1)
            if s.session_id != session_id][:PAST_SESSION_LIMIT]
    rows = []
    for s in past:
        count = repo.session_message_count(s.session_id)
        summary = (s.running_summary or "").strip()
        rows.append(f"• {s.title[:60]} ({count} msgs)"
                    + (f"\n    {summary[:200]}" if summary else ""))
    running = session.running_summary if session else ""
    if running:
        rows.insert(0, f"[this call so far] {running}")
    out.append(_section(4, "ALL PAST CHATS SUMMARY", "\n".join(rows),
                        f"max {PAST_SESSION_LIMIT} sessions"))

    # 5 — menu (abbreviated for the console only)
    full_menu = format_menu_for_prompt()
    out.append(_section(5, "MENU", abbreviate(full_menu, 100),
                        f"abbreviated · model receives full "
                        f"~{len(full_menu) // config.CHARS_PER_TOKEN} tokens"))

    return "\n".join(out)


def print_context_report(repo, user_id: str, session_id: str, user_message: str) -> None:
    print(build_context_report(repo, user_id, session_id, user_message), flush=True)
