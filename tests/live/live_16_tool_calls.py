"""LIVE — prove the real model invokes price_order rather than doing mental math.

Instruments orders.tools.run_tool and asserts a real invocation occurred with
correct structured arguments.
"""
import sys, pathlib, os, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import config
config.DEBUG_CONTEXT = False          # keep the output readable

import orders.tools as tools
from orders.calculator import price_order
from providers.openai_provider import OpenAIProvider
from service import handle_message
from storage.sqlite_store import SQLiteStore

CALLS = []
_orig_run = tools.run_tool


def _spy(name, arguments):
    result = _orig_run(name, arguments)
    CALLS.append({"tool": name, "args": arguments, "result": result})
    return result


tools.run_tool = _spy


def main():
    db = os.path.join(tempfile.mkdtemp(), "tool.db")
    repo = SQLiteStore(db); repo.init_db()
    provider = OpenAIProvider()
    sid = repo.create_session("+919876543210").session_id

    for text in ["Two samosas and one gobi manchurian please.",
                 "That's everything. What's my total?"]:
        out = handle_message(repo, provider, "+919876543210", sid, text)
        print(f"caller> {text}\nagent > {out['answer']}\n")

    print("=" * 60)
    print(f"TOOL INVOCATIONS: {len(CALLS)}")
    for c in CALLS:
        print(f"  {c['tool']}({c['args']})")
        print(f"    -> {c['result'][:120]}")

    priced = [c for c in CALLS if c["tool"] == "price_order"]
    called = bool(priced)

    # the arguments the model produced must match what was ordered
    args_ok = False
    if priced:
        items = json.loads(priced[-1]["args"]).get("items", [])
        got = {i["name"].lower(): i.get("quantity") for i in items}
        args_ok = got.get("samosa") == 2 and any(
            "manchurian" in k for k in got)

    truth = price_order([{"name": "Samosa", "quantity": 2},
                         {"name": "Gobi Manchurian", "quantity": 1}])
    result_ok = priced and json.loads(priced[-1]["result"])["total"] == truth["total"]

    print()
    print(f"price_order invoked        : {called}")
    print(f"arguments match the order  : {args_ok}")
    print(f"tool total == ground truth : {bool(result_ok)}  (${truth['total']:.2f})")
    repo.close()
    ok = called and args_ok and result_ok
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
