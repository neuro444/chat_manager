"""Deterministic provider for tests: no network, no cost, no surprises.

`last_messages` records exactly what the pipeline sent, which is how context
assembly gets asserted on.
"""
from typing import Iterator


class FakeProvider:
    def __init__(self, reply: str = "This is a fake reply."):
        self.reply = reply
        self.last_messages: list[dict] | None = None
        self.call_count = 0

    def complete(self, messages: list[dict], **kw) -> str:
        self.last_messages = messages
        self.call_count += 1
        return self.reply

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
