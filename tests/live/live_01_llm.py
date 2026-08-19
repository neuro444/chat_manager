"""LIVE test — hits the real OpenAI API. Run deliberately, costs money.

    python tests/live/live_01_llm.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from context.assembler import assemble
from providers.openai_provider import OpenAIProvider


def main():
    provider = OpenAIProvider()

    messages = assemble(
        user_message="What is my name and what am I building?",
        history=[
            {"role": "user", "content": "Hi, I'm Sree."},
            {"role": "assistant", "content": "Nice to meet you, Sree!"},
        ],
        summary="",
        memory="",
        profile="Name: Sree",
        domain="The user is building a chat management boilerplate in Python.",
    )

    print("=== PROMPT SENT ===")
    for m in messages:
        print(f"[{m['role']}] {m['content'][:200]}")

    print("\n=== CALLING OPENAI ===")
    answer = provider.complete(messages)
    print(f"\n=== REPLY ===\n{answer}\n")

    ok = "sree" in answer.lower()
    print(f"Context was used (name recalled): {ok}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
