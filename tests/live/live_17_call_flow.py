"""LIVE — ambiguity handled once, delivery redirect, pickup sign-off, end flag."""
import sys, pathlib, os, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import config; config.DEBUG_CONTEXT = False

from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore


def call(repo, p, phone, turns):
    sid, answers = repo.create_session(phone).session_id, []
    for t in turns:
        out = handle_message(repo, p, phone, sid, t)
        answers.append(out)
        print(f"caller> {t}\nagent > {out['answer']}"
              f"{'   [CALL ENDED]' if out['call_ended'] else ''}\n")
    return answers


def main():
    db = os.path.join(tempfile.mkdtemp(), "flow.db")
    repo = SQLiteStore(db); repo.init_db()
    p = OpenAIProvider()

    print("═══ A. AMBIGUOUS ITEM + PICKUP ═══")
    a = call(repo, p, "+911", [
        "Hi, I'd like one chicken biryani.",
        "Yes that's fine.",
        "Pickup please. That's everything.",
        "Yes, that works.",
    ])
    asked_once = sum("biriyani" in x["answer"].lower()
                     and "?" in x["answer"] for x in a[:2]) <= 2
    signoff = "cakeworld alpharetta" in a[-1]["answer"].lower()
    ended_a = a[-1]["call_ended"]

    print("═══ B. NOT ON THE MENU ═══")
    b = call(repo, p, "+912", ["Do you have Malayalee chicken biryani?"])
    offered = "malabar" in b[0]["answer"].lower() or "chettinad" in b[0]["answer"].lower()

    print("═══ C. DELIVERY REDIRECT ═══")
    c = call(repo, p, "+913", [
        "I want two samosas delivered to my house.",
        "No thanks, I'll just order online.",
    ])
    website = any("cakeworldeatery.com" in x["answer"].lower() for x in c)
    ended_c = c[-1]["call_ended"]

    print("=" * 60)
    print(f"A: clarified without looping   : {asked_once}")
    print(f"A: pickup sign-off present     : {signoff}")
    print(f"A: call flagged ended          : {ended_a}")
    print(f"B: offered a real menu item    : {offered}")
    print(f"C: gave the delivery website   : {website}")
    print(f"C: call flagged ended          : {ended_c}")
    repo.close()
    ok = all([asked_once, signoff, ended_a, offered, website])
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
