"""Standalone OpenAI Responses API connectivity check.

Loads OPENAI_API_KEY and optional model settings from the project's .env file.
This intentionally does not import the chat manager provider or service code.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY is missing from .env", file=sys.stderr)
        return 1

    model = os.getenv("LLM_MODEL", "gpt-5.6-luna").strip()
    temperature = float(os.getenv("TEMPERATURE", "1"))

    print(f"Testing model={model} temperature={temperature}")

    try:
        response = OpenAI(api_key=api_key).responses.create(
            model=model,
            input="Reply with exactly: LLM_OK",
            temperature=temperature,
            max_output_tokens=50,
            store=False,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"SUCCESS: {response.output_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
