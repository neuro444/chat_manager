"""LIVE — cross-session memory + user scoping against the real API and DB."""
import sys, pathlib, os, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore

def main():
    db = os.path.join(tempfile.mkdtemp(), "cross.db")
    repo = SQLiteStore(db); repo.init_db()
    p = OpenAIProvider()

    print("=== SESSION A (sree states a fact) ===")
    a = handle_message(repo, p, "sree", None,
        "Remember this: my project codename is Nightingale and it uses Redis.")
    print(f"you> my project codename is Nightingale and it uses Redis.")
    print(f"bot> {a['answer'][:120]}")

    print("\n=== SESSION B (new session, same user) ===")
    b = handle_message(repo, p, "sree", None, "What is my project codename?")
    print(f"you> What is my project codename?")
    print(f"bot> {b['answer']}")
    recalled = "nightingale" in b["answer"].lower()

    print("\n=== SESSION C (different user: bob) ===")
    c = handle_message(repo, p, "bob", None, "What is my project codename?")
    print(f"you> What is my project codename?")
    print(f"bot> {c['answer'][:160]}")
    leaked = "nightingale" in c["answer"].lower()

    print("\n" + "="*55)
    print(f"Cross-session recall (sree)   : {recalled}")
    print(f"Leaked to other user (bob)    : {leaked}")
    repo.close()
    ok = recalled and not leaked
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
