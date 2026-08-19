"""OpenAI adapter built on the Responses API.

Responses is OpenAI's current interface (Chat Completions is legacy; the
Assistants API sunsets in H1 2026). Differences that matter here:
  - `input=` carries the message array, not `messages=`
  - the system prompt goes in `instructions=`, not a system-role message
  - `max_output_tokens=` replaces `max_tokens=`
  - `.output_text` aggregates the reply text
  - streaming emits typed events; text arrives on `response.output_text.delta`

Key is read from OPENAI_API_KEY in the environment only.
"""
import time
from typing import Iterator

from openai import APIError, OpenAI, RateLimitError

import config


def split_instructions(messages: list[dict]) -> tuple[str, list[dict]]:
    """Separate leading system messages from the conversation turns.

    The assembler emits system blocks first; Responses wants those as
    `instructions` and only user/assistant turns in `input`.
    """
    instructions = "\n\n".join(
        m["content"] for m in messages if m.get("role") == "system"
    )
    # Tool items (function_call / function_call_output) carry no role and must
    # pass through to `input` untouched.
    turns = [m for m in messages if m.get("role") != "system"]
    return instructions, turns


class OpenAIProvider:
    def __init__(self, model: str | None = None):
        self.client = OpenAI()
        self.model = model or config.LLM_MODEL
        self.last_tools_called = False

    def _create(self, messages: list[dict], stream: bool = False, tools=None):
        instructions, turns = split_instructions(messages)
        return self.client.responses.create(
            model=self.model,
            instructions=instructions or None,
            input=turns,
            temperature=config.TEMPERATURE,
            max_output_tokens=config.MAX_TOKENS,
            store=False,          # we own persistence; don't retain server-side
            stream=stream,
            **({"tools": tools} if tools else {}),
        )

    def complete(self, messages: list[dict], tools=None, **kw) -> str:
        self.last_tools_called = False
        last_err = None
        for attempt in range(config.MAX_RETRIES):
            try:
                if tools:
                    return self._complete_with_tools(messages, tools)
                return self._create(messages).output_text or ""
            except (RateLimitError, APIError) as err:
                last_err = err
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(2**attempt)
        raise RuntimeError(f"LLM unavailable after retries: {last_err}")

    def _complete_with_tools(self, messages: list[dict], tools) -> str:
        """One round of tool use: call, run any tool, feed results back."""
        from orders.tools import TOOL_SCHEMAS, run_tool

        convo = list(messages)
        resp = self._create(convo, tools=TOOL_SCHEMAS)
        calls = [o for o in (resp.output or [])
                 if getattr(o, "type", "") == "function_call"]
        if not calls:
            return resp.output_text or ""

        self.last_tools_called = True

        for call in calls:
            result = run_tool(call.name, call.arguments)
            convo.append({"type": "function_call", "call_id": call.call_id,
                          "name": call.name, "arguments": call.arguments})
            convo.append({"type": "function_call_output",
                          "call_id": call.call_id, "output": result})
        return self._create(convo, tools=TOOL_SCHEMAS).output_text or ""

    def stream(self, messages: list[dict], **kw) -> Iterator[str]:
        for event in self._create(messages, stream=True):
            if getattr(event, "type", None) == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if delta:
                    yield delta

    def count_tokens(self, text: str) -> int:
        return len(text) // config.CHARS_PER_TOKEN

    def transcribe(self, audio_path: str) -> str:
        """STT. gpt-transcribe is the current default; whisper-1 still works."""
        with open(audio_path, "rb") as fh:
            result = self.client.audio.transcriptions.create(
                model=config.STT_MODEL, file=fh
            )
        return result.text
