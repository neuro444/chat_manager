"""Rolling summary — compaction of turns that fell out of the window."""
import config
from prompts import SUMMARIZER_PROMPT


def should_roll(repo, session_id: str) -> bool:
    session = repo.get_session(session_id)
    if not session:
        return False
    total = repo.message_count(session_id)
    return (total - session.summarized_upto) >= config.SUMMARY_TRIGGER_EVERY


def maybe_roll_summary(repo, provider, session_id: str) -> str | None:
    """Compact older turns into the running summary. Call AFTER replying."""
    if not should_roll(repo, session_id):
        return None

    session = repo.get_session(session_id)
    total = repo.message_count(session_id)
    cutoff = max(total - config.HISTORY_WINDOW, 0)
    if cutoff <= session.summarized_upto:
        return None

    all_msgs = repo.all_messages(session_id)
    to_fold = all_msgs[session.summarized_upto : cutoff]
    if not to_fold:
        return None

    transcript = "\n".join(f"{m.role}: {m.content}" for m in to_fold)
    prior = f"Previous summary:\n{session.running_summary}\n\n" if session.running_summary else ""

    messages = [
        {"role": "system", "content": SUMMARIZER_PROMPT},
        {"role": "user", "content": f"{prior}Conversation to summarize:\n{transcript}"},
    ]
    summary = provider.complete(messages)
    repo.update_summary(session_id, summary.strip(), cutoff)
    return summary.strip()
