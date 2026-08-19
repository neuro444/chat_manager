"""Caller name capture.

Names arrive mid-sentence on a phone call ("Hi, this is Priya"). Captured once,
then reused so the agent can greet returning callers by name.
"""
import re

# Case-insensitive throughout: a transcript may capitalize a sentence-initial
# "This is Priya" or lowercase everything.
_PATTERNS = [
    re.compile(r"\bthis is ([a-z][a-z'-]{1,20})\b", re.I),
    re.compile(r"\bmy name is ([a-z][a-z'-]{1,20})\b", re.I),
    re.compile(r"\bname'?s ([a-z][a-z'-]{1,20})\b", re.I),
    re.compile(r"\bit'?s ([a-z][a-z'-]{1,20}) (?:here|calling|again)\b", re.I),
    re.compile(r"\bi'?m ([a-z][a-z'-]{1,20})\b", re.I),
]

# Words that can follow "I'm" / "this is" but are not names.
_NOT_NAMES = {
    "calling", "looking", "trying", "just", "here", "good", "fine", "ordering",
    "wondering", "hoping", "still", "not", "sorry", "back", "done", "ready",
    "for", "the", "a", "an", "my", "your", "his", "her", "their", "our",
    "going", "about", "interested", "hungry", "waiting", "with", "from",
    "pickup", "delivery", "correct", "right", "okay", "ok", "all", "everything",
    "that", "this", "it", "he", "she", "they", "we", "you", "sure", "great",
    "gonna", "trying", "hoping", "afraid", "glad", "happy", "new", "regular",
}


def extract_name(text: str) -> str | None:
    for pat in _PATTERNS:
        m = pat.search(text or "")
        if m:
            name = m.group(1).strip()
            if name.lower() not in _NOT_NAMES and len(name) > 1:
                return name.capitalize()
    return None


def capture_name(repo, user_id: str, text: str) -> str | None:
    """Store the caller's name the first time they give it."""
    user = repo.get_user(user_id)
    if user and user.name:
        return user.name
    name = extract_name(text)
    if name:
        repo.set_user_name(user_id, name)
    return name
