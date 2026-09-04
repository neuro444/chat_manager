"""Deterministic provider for tests: no network, no cost, no surprises.

`last_messages` records exactly what the pipeline sent, which is how context
assembly gets asserted on.
"""
import json
from typing import Iterator

from pydantic import ValidationError

from context.response_model import CallResponse


def _as_validated(reply: str):
    """Return a CallResponse when the canned reply is a full contract object."""
    if not isinstance(reply, str):
        return reply
    text = reply.strip()
    if not text.startswith("{"):
        return reply
    try:
        return CallResponse.model_validate_json(text)
    except ValidationError:
        # A partial JSON fixture is not the contract; hand back the dict so the
        # parser normalizes it exactly as before.
        return json.loads(text)


class FakeProvider:
    def __init__(self, reply: str = "This is a fake reply.", tool_results=None):
        self.reply = reply
        self.last_messages: list[dict] | None = None
        self.call_count = 0
        self.last_tool_results = tool_results or []
        self.last_tools_called = bool(self.last_tool_results)

    def complete(self, messages: list[dict], **kw):
        """Mirror the real provider: a canned JSON reply arrives validated.

        Tests that pass a plain sentence still get a plain sentence, which the
        parser treats as speech with no control flags — the same way the
        summarizer's free-text replies are handled.
        """
        self.last_messages = messages
        self.call_count += 1
        return _as_validated(self.reply)

    def stream(self, messages: list[dict], **kw) -> Iterator[str]:
        self.last_messages = messages
        self.call_count += 1
        for word in self.reply.split():
            yield word + " "

    def count_tokens(self, text: str) -> int:
        return len(text) // 4


class EchoProvider(FakeProvider):
    """Echoes back what it received — useful for inspecting the final prompt."""

    def complete(self, messages: list[dict], **kw) -> str:
        self.last_messages = messages
        self.call_count += 1
        return messages[-1]["content"]
