"""OpenAI adapter built on the Responses API.

Responses is OpenAI's current interface (Chat Completions is legacy; the
Assistants API sunsets in H1 2026). Differences that matter here:
  - `input=` carries the message array, not `messages=`
  - the system prompt goes in `instructions=`, not a system-role message
  - `max_output_tokens=` replaces `max_tokens=`
  - `.output_text` aggregates the reply text
  - streaming emits typed events; text arrives on `response.output_text.delta`

Non-streaming turns use `responses.parse(text_format=CallResponse)`, so the
model's output is schema-constrained and arrives already validated. Callers
receive a CallResponse, never raw text to be parsed.

Key is read from OPENAI_API_KEY in the environment only.
"""
import json
import time
from typing import Iterator

from openai import APIError, OpenAI, RateLimitError

import config
from context.response_model import CallResponse


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
        self.last_tool_results: list[dict] = []
        # Exact token usage reported by the API for the most recent turn.
        # Summed across tool round trips, since one caller turn can be
        # several API calls and you are billed for all of them.
        self.last_usage: dict | None = None

    def _record_usage(self, response) -> None:
        """Accumulate the API's reported usage for this turn."""
        from tokens import usage_from_response

        usage = usage_from_response(response)
        if usage is None:
            return
        if self.last_usage is None:
            self.last_usage = usage
            return
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            self.last_usage[key] += usage[key]

    def _create(self, messages: list[dict], stream: bool = False, tools=None):
        """Structured Outputs call. `parse` constrains generation to CallResponse.

        Streaming cannot be schema-constrained the same way, so it stays on
        `create`; see `stream` below for why that is safe here.
        """
        instructions, turns = split_instructions(messages)
        kwargs = dict(
            model=self.model,
            instructions=instructions or None,
            input=turns,
            temperature=config.TEMPERATURE,
            max_output_tokens=config.MAX_TOKENS,
            store=False,          # we own persistence; don't retain server-side
            **({"tools": tools} if tools else {}),
        )
        if stream:
            return self.client.responses.create(stream=True, **kwargs)
        return self.client.responses.parse(text_format=CallResponse, **kwargs)

    def complete(self, messages: list[dict], tools=None, **kw) -> CallResponse:
        self.last_tools_called = False
        self.last_tool_results = []
        self.last_usage = None
        last_err = None
        for attempt in range(config.MAX_RETRIES):
            try:
                if tools:
                    return self._complete_with_tools(messages, tools)
                response = self._create(messages)
                self._record_usage(response)
                return response.output_parsed
            except (RateLimitError, APIError) as err:
                last_err = err
                if attempt < config.MAX_RETRIES - 1:
                    time.sleep(2**attempt)
        raise RuntimeError(f"LLM unavailable after retries: {last_err}")

    def _complete_with_tools(self, messages: list[dict], tools) -> CallResponse:
        """One round of tool use: call, run any tool, feed results back."""
        from orders.tools import TOOL_SCHEMAS, run_tool

        convo = list(messages)
        resp = self._create(convo, tools=TOOL_SCHEMAS)
        self._record_usage(resp)
        calls = [o for o in (resp.output or [])
                 if getattr(o, "type", "") == "function_call"]
        if not calls:
            return resp.output_parsed

        self.last_tools_called = True

        for call in calls:
            result = run_tool(call.name, call.arguments)
            try:
                parsed_result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                parsed_result = result
            self.last_tool_results.append({
                "name": call.name,
                "result": parsed_result,
            })
            convo.append({"type": "function_call", "call_id": call.call_id,
                          "name": call.name, "arguments": call.arguments})
            convo.append({"type": "function_call_output",
                          "call_id": call.call_id, "output": result})
        final = self._create(convo, tools=TOOL_SCHEMAS)
        self._record_usage(final)
        return final.output_parsed

    def stream(self, messages: list[dict], **kw) -> Iterator[str]:
        # Streaming currently exposes no ordering tools, so it can never carry
        # a ready order from a previous non-streaming turn.
        self.last_tools_called = False
        self.last_tool_results = []
        self.last_usage = None
        for event in self._create(messages, stream=True):
            if getattr(event, "type", None) == "response.output_text.delta":
                delta = getattr(event, "delta", None)
                if delta:
                    yield delta

    def count_tokens(self, text: str) -> int:
        from tokens import count_text

        return count_text(text)

    def transcribe(self, audio_path: str) -> str:
        """STT. gpt-transcribe is the current default; whisper-1 still works."""
        with open(audio_path, "rb") as fh:
            result = self.client.audio.transcriptions.create(
                model=config.STT_MODEL, file=fh
            )
        return result.text
