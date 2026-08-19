"""LIVE — MongoDB adapter against the local server. Uses its OWN database."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from providers.fake_provider import FakeProvider
from service import build_context, handle_message
from storage.mongo_store import MongoStore

DB = "chat_manager_livetest"

def main():
    repo = MongoStore(db_name=DB)
    repo.db.client.admin.command("ping")
    print(f"connected; using database {DB!r}")
    for c in ("users", "sessions", "messages", "counters"):
        repo.db[c].delete_many({})
    repo.init_db()
    p = FakeProvider("mongo reply")

    out = handle_message(repo, p, "sree", None, "my favourite editor is Neovim")
    sid = out["session_id"]
    handle_message(repo, p, "sree", sid, "second turn")
    msgs = repo.all_messages(sid)
    print(f"messages persisted : {len(msgs)}")
    print(f"seq order          : {[m.seq for m in msgs]}")

    # reconnect = new client, proves durability
    repo2 = MongoStore(db_name=DB)
    again = repo2.all_messages(sid)
    print(f"after reconnect    : {len(again)} messages")

    b = repo2.create_session("sree").session_id
    blob = "\n".join(m["content"] for m in build_context(repo2, "sree", b, "what editor do I use?"))
    recalled = "neovim" in blob.lower()
    print(f"cross-session recall: {recalled}")

    bob = repo2.create_session("bob").session_id
    bblob = "\n".join(m["content"] for m in build_context(repo2, "bob", bob, "what editor do I use?"))
    leaked = "neovim" in bblob.lower()
    print(f"leaked to bob       : {leaked}")

    counts = {c: repo2.db[c].count_documents({}) for c in ("users","sessions","messages")}
    print(f"collections         : {counts}")

    ok = len(again) == 4 and recalled and not leaked
    print("PASS" if ok else "FAIL")
    repo.close(); repo2.close()
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
