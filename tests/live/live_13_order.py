"""LIVE — full order with menu, tool-based pricing, name capture, expiry."""
import sys, pathlib, os, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from orders.calculator import price_order
from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore

PHONE = "+919876543210"

def main():
    db = os.path.join(tempfile.mkdtemp(), "order.db")
    repo = SQLiteStore(db); repo.init_db()
    p = OpenAIProvider()
    sid = None

    def say(t):
        nonlocal sid
        out = handle_message(repo, p, PHONE, sid, t)
        sid = out["session_id"]
        print(f"caller> {t}\nagent > {out['answer']}\n")
        return out["answer"]

    print("═══ CALL 1 ═══")
    say("Hi, this is Priya. What veg appetizers do you have?")
    say("I'll take two samosas and one gobi manchurian.")
    last = say("What's my total?")

    truth = price_order([{"name": "Samosa", "quantity": 2},
                         {"name": "Gobi Manchurian", "quantity": 1}])
    print("─" * 55)
    print(f"Ground truth: subtotal ${truth['subtotal']:.2f} "
          f"tax ${truth['tax']:.2f} total ${truth['total']:.2f}")

    # The prompt requires prices spoken as words ("twenty-five eighty-three"),
    # so accept either the digits or the spoken form.
    WORDS = {0:"zero",1:"one",2:"two",3:"three",4:"four",5:"five",6:"six",
             7:"seven",8:"eight",9:"nine",10:"ten",11:"eleven",12:"twelve",
             13:"thirteen",14:"fourteen",15:"fifteen",16:"sixteen",
             17:"seventeen",18:"eighteen",19:"nineteen",20:"twenty",
             30:"thirty",40:"forty",50:"fifty",60:"sixty",70:"seventy",
             80:"eighty",90:"ninety"}
    def spoken_forms(n):
        if n in WORDS: return {WORDS[n]}
        tens, ones = divmod(n, 10)
        if tens*10 in WORDS and ones in WORDS:
            return {f"{WORDS[tens*10]}-{WORDS[ones]}", f"{WORDS[tens*10]} {WORDS[ones]}"}
        return set()
    dollars, cents = divmod(int(round(truth["total"]*100)), 100)
    low = last.lower().replace(",", "")
    total_ok = (f"{truth['total']:.2f}" in low
                or any(d in low and c in low
                       for d in spoken_forms(dollars) for c in spoken_forms(cents)))
    name = repo.get_user(PHONE).name
    print(f"Total quoted correctly : {total_ok}")
    print(f"Name captured          : {name!r}")

    print("\n═══ CALL 2 — new session, returning caller ═══")
    sid = repo.create_session(PHONE).session_id
    ans = say("Hi, it's me. What did I get last time?")
    recalled = "samosa" in ans.lower()
    print(f"Recalled past order    : {recalled}")

    repo.close()
    ok = total_ok and name == "Priya" and recalled
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
