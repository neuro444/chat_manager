"""Layer 1 — LLM call with assembled context.

Proves: a prompt built from a system prompt + context + history reaches the
provider in the right shape, and a reply comes back.
"""
import pytest
from providers.fake_provider import FakeProvider
from context.assembler import assemble


def test_assemble_puts_system_prompt_first():
    msgs = assemble("hello", history=[], summary="", memory="", profile="")
    assert msgs[0]["role"] == "system"
    assert len(msgs[0]["content"]) > 0


def test_assemble_puts_user_message_last():
    msgs = assemble("my question", history=[], summary="", memory="", profile="")
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "my question"


def test_assemble_includes_history_between():
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    msgs = assemble("new question", history=history, summary="", memory="", profile="")
    contents = [m["content"] for m in msgs]
    assert "earlier question" in contents
    assert "earlier answer" in contents
    assert contents.index("earlier answer") < contents.index("new question")


def test_context_blocks_appear_when_provided():
    msgs = assemble("q", history=[], summary="SUMMARY_TEXT",
                    memory="MEMORY_TEXT", profile="Name: Sree")
    blob = "\n".join(m["content"] for m in msgs)
    assert "SUMMARY_TEXT" in blob
    assert "MEMORY_TEXT" in blob
    assert "Sree" in blob


def test_no_empty_context_block_when_nothing_provided():
    msgs = assemble("q", history=[], summary="", memory="", profile="")
    # only system prompt + user message
    assert len(msgs) == 2


def test_provider_receives_assembled_messages_and_replies():
    provider = FakeProvider("canned reply")
    msgs = assemble("hello", history=[], summary="", memory="", profile="")
    answer = provider.complete(msgs)
    assert answer == "canned reply"
    assert provider.last_messages == msgs
