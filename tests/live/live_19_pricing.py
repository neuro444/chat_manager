"""LIVE — menu price while discussing, tool total only at the review."""
import sys, pathlib, os, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import config; config.DEBUG_CONTEXT = False

from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore


def main():
    repo = SQLiteStore(os.path.join(tempfile.mkdtemp(), "p.db")); repo.init_db()
    p = OpenAIProvider()
    sid = repo.create_session("+915").session_id
    outs = []
    for t in ["How much is the Malabar Chicken Biriyani?",
              "I'll take one of those and two samosas.",
              "That's everything, pickup please."]:
        o = handle_message(repo, p, "+915", sid, t)
        outs.append(o["answer"])
        print(f"caller> {t}\nagent > {o['answer']}\n")

    a0 = outs[0].lower().replace("-", " ")
    # $15.99 menu price, NOT $17.23 (taxed)
    quoted_menu = "fifteen ninety nine" in a0 or "15.99" in a0
    quoted_taxed = "seventeen twenty three" in a0 or "17.23" in a0

    final = outs[-1].lower().replace("-", " ")
    units = ("five ninety nine" in final or "5.99" in final) and \
            ("fifteen ninety nine" in final or "15.99" in final)
    total = "thirty" in final or "30.14" in final

    print("=" * 58)
    print(f"Discussion quoted MENU price (15.99) : {quoted_menu}")
    print(f"Discussion leaked TAXED price (17.23): {quoted_taxed}")
    print(f"Review read back unit prices         : {units}")
    print(f"Review gave the total                : {total}")
    repo.close()
    ok = quoted_menu and not quoted_taxed and units and total
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
