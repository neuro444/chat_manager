"""Entity carry-over so short follow-ups resolve to the right subject.

Pure heuristic — no LLM call. Override `extract_entities` per project.
Hard rule: only ever inherit what the user already said; never invent.
"""
import re

import config

_PROPER = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_QUOTED = re.compile(r'"([^"]{2,40})"')

# Sentence-initial words are capitalized by grammar, not because they name a thing.
_COMMON_STARTERS = {
    # Sentence-initial verbs / questions / pronouns — capitalized by grammar,
    # not because they name a thing.
    "The", "This", "That", "These", "Those", "What", "When", "Where", "Who",
    "Why", "How", "Which", "Can", "Could", "Should", "Would", "Will", "Does",
    "Did", "Are", "Is", "Was", "Were", "Have", "Has", "Had", "It", "They",
    "There", "Here", "Tell", "Explain", "Give", "Show", "Compare", "Describe",
    "List", "Find", "Help", "Make", "Let", "Please", "Now", "Then", "Also",
    "But", "And", "Or", "So", "If", "Hi", "Hello", "Hey", "Yes", "No", "Okay",
    "Sure", "Thanks", "Thank", "My", "Your", "Our", "Their", "His", "Her",
    "I", "We", "You", "Some", "Any", "All", "Both", "More", "Most", "Next",
    "Continue", "Again", "Still", "Just", "Only", "Well", "Good", "Great",
}


def extract_entities(text: str) -> list[str]:
    found = [w for w in _PROPER.findall(text) if w not in _COMMON_STARTERS]
    found += _QUOTED.findall(text)
    seen, out = set(), []
    for f in found:
        if f.lower() not in seen:
            seen.add(f.lower())
            out.append(f)
    return out


def resolve_active_entities(repo, session_id: str, user_message: str) -> list[str]:
    """Explicit entities win; otherwise inherit from the last turn that had any."""
    explicit = extract_entities(user_message)
    if explicit:
        return explicit
    recent = repo.recent_messages(session_id, config.CARRY_OVER_SCAN_LIMIT)
    for msg in reversed(recent):
        if msg.role != "user":
            continue
        prior = extract_entities(msg.content)
        if prior:
            return prior
    return []
