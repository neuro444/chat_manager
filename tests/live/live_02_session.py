"""LIVE — session memory across turns against the real API."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.memory_store import MemoryStore


def main():
    repo, provider = MemoryStore(), OpenAIProvider()
    repo.init_db()
    user = "sree"

    turns = [
        "Hi, my name is Sree and I'm building a chat manager in Python.",
        "What is my name?",
        "And what am I building?",
    ]

    sid = None
    answers = []
    for t in turns:
        out = handle_message(repo, provider, user, sid, t)
        sid = out["session_id"]
        answers.append(out["answer"])
        print(f"\nyou> {t}")
        print(f"bot> {out['answer']}")

    print("\n" + "=" * 55)
    name_ok = "sree" in answers[1].lower()
    proj_ok = any(w in answers[2].lower() for w in ("chat", "python", "manager"))
    print(f"Turn 2 recalled the name       : {name_ok}")
    print(f"Turn 3 recalled the project    : {proj_ok}")
    print(f"Messages persisted             : {repo.message_count(sid)}")
    print(f"Session title                  : {repo.get_session(sid).title!r}")
    ok = name_ok and proj_ok
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
