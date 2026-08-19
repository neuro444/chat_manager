"""LIVE — streaming via the Responses API."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from context.assembler import assemble
from providers.openai_provider import OpenAIProvider


def main():
    provider = OpenAIProvider()
    messages = assemble("Count from 1 to 5, words only.", history=[])
    print("=== STREAMING ===")
    chunks = 0
    out = []
    for delta in provider.stream(messages):
        print(delta, end="", flush=True)
        out.append(delta)
        chunks += 1
    text = "".join(out)
    print(f"\n\nchunks received: {chunks}")
    ok = chunks > 1 and len(text) > 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
