"""LIVE — context console output + name discipline across a full call."""
import sys, pathlib, os, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import config
config.DEBUG_CONTEXT = True

from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore

PHONE = "+919876543210"

def main():
    db = os.path.join(tempfile.mkdtemp(), "ctx.db")
    repo = SQLiteStore(db); repo.init_db()
    p = OpenAIProvider()

    # seed a prior call so contexts 3 and 4 have content
    old = repo.create_session(PHONE, "Previous call")
    repo.append_message(old.session_id, "user", "This is Priya, one chicken biryani")
    repo.append_message(old.session_id, "assistant", "Got it, one chicken biryani.")
    repo.set_user_name(PHONE, "Priya")

    # Start an explicitly NEW session; passing None would resume the seeded
    # call (it is within the 5-minute window), leaving contexts 3 and 4 empty.
    sid = repo.create_session(PHONE).session_id
    answers = []
    for text in ["Hi, it's Priya again. Two samosas please.",
                 "Add one gobi manchurian.",
                 "That's all, nothing else. What's my total?"]:
        out = handle_message(repo, p, PHONE, sid, text)
        sid = out["session_id"]
        answers.append(out["answer"])
        print(f"\ncaller> {text}\nagent > {out['answer']}\n")

    print("=" * 72)
    used = [i + 1 for i, a in enumerate(answers) if "priya" in a.lower()]
    print(f"Replies using the name: {used or 'none'} (of {len(answers)})")
    print(f"Name used at most twice: {len(used) <= 2}")
    repo.close()
    return 0 if len(used) <= 2 else 1

if __name__ == "__main__":
    sys.exit(main())
