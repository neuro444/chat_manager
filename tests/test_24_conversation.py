"""Layer 24 — multi-turn conversation structure.

These use a scripted provider, so they assert what the PIPELINE does with a
sequence of turns: that state survives, that the prompt reaching the model still
carries the caller's earlier words, and that the response contract holds across
a call. They cannot prove the live model behaves correctly — only a live replay
does that — but they catch structural regressions for free in CI.
"""
import json

import pytest

from context.response_model import CallResponse
from service import handle_message


def _reply(answer, **flags):
    return json.dumps({
        "answer": answer, "call_ended": False, "order_ready": False,
        "order": None, "order_type": None, "user_name": None, "name": None,
        "To_manager": False, "Transfer_to_Manager": False,
        "tools_called": False, "summary": "", "verbatim_user_chat": [],
        **flags,
    })


class ScriptedProvider:
    """Replies from a fixed list, recording the prompt sent for each turn."""

    def __init__(self, replies):
        self._replies = list(replies)
        self._i = 0
        self.prompts: list[str] = []
        self.last_messages = None
        self.last_tool_results: list[dict] = []
        self.last_tools_called = False

    def complete(self, messages, **kw):
        self.last_messages = messages
        self.prompts.append("\n".join(
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        ))
        reply = self._replies[min(self._i, len(self._replies) - 1)]
        self._i += 1
        return CallResponse.model_validate_json(reply)

    def count_tokens(self, text: str) -> int:
        return len(text) // 4


def _run(repo, turns, replies, user="+15550101"):
    """Drive a whole call, returning the provider and every result."""
    provider = ScriptedProvider(replies)
    sid, results = None, []
    for turn in turns:
        out = handle_message(repo, provider, user, sid, turn)
        sid = out["session_id"]
        results.append(out)
    return provider, results


def test_mid_call_greeting_does_not_lose_the_order(repo):
    """The hello-restart bug: earlier items must still be in the prompt."""
    provider, results = _run(
        repo,
        ["I'd like two samosas for pickup", "hello? are you there?"],
        [_reply("Two Samosas for pickup. Anything else?", order_type="pickup"),
         _reply("Yes, I'm here. I have two Samosas for pickup.",
                order_type="pickup")],
    )
    resumed = provider.prompts[-1]
    assert "two samosas" in resumed.lower()
    assert "pickup" in resumed.lower()
    assert results[-1]["call_ended"] is False


def test_catering_details_stay_in_context_after_a_bare_yes(repo):
    """The catering-restart bug: headcount and day survive a non-answer."""
    provider, _ = _run(
        repo,
        ["I need catering for fifty people on Saturday around three",
         "mostly vegetarian",
         "yes"],
        [_reply("Catering is handled by my manager. May I have the order details, please?",
                order_type="catering"),
         _reply("Got it. Any preference on spice level?", order_type="catering"),
         _reply("I have fifty people, Saturday around three, mostly vegetarian.",
                order_type="catering")],
    )
    final = provider.prompts[-1].lower()
    for detail in ("fifty", "saturday", "vegetarian"):
        assert detail in final, detail


def test_established_fulfillment_survives_later_turns(repo):
    """Pickup stated early must still be visible when food is settled."""
    provider, _ = _run(
        repo,
        ["it's for pickup", "one chilli paneer", "that's all"],
        [_reply("Sure, pickup. What would you like?", order_type="pickup"),
         _reply("One Chilli Paneer. Anything else?", order_type="pickup"),
         _reply("What name should I place the order under?", order_type="pickup")],
    )
    assert "pickup" in provider.prompts[-1].lower()


def test_a_correction_keeps_the_corrected_value_in_context(repo):
    provider, _ = _run(
        repo,
        ["a birthday cake for tonight", "actually make it three days from now"],
        [_reply("Cake orders are handled by my manager. May I have the order details, please?",
                order_type="cake"),
         _reply("Noted, three days from now instead of tonight.", order_type="cake")],
    )
    assert "three days" in provider.prompts[-1].lower()


def test_every_turn_returns_the_validated_contract(repo):
    _, results = _run(
        repo,
        ["hi", "two samosas", "that's all"],
        [_reply("Hi, I'm Divya."), _reply("Two Samosas."), _reply("Thanks.")],
    )
    for out in results:
        assert isinstance(out["answer"], str) and out["answer"]
        assert "{" not in out["answer"]
        for flag in ("call_ended", "order_ready", "To_manager",
                     "Transfer_to_Manager", "tools_called"):
            assert isinstance(out[flag], bool)


def test_order_ready_is_refused_without_a_pricing_tool_result(repo):
    """A model claiming completion cannot manufacture an order."""
    _, results = _run(
        repo,
        ["two samosas for pickup, that's all", "Priya"],
        [_reply("What name should I place the order under?", order_type="pickup"),
         _reply("Thanks Priya, ready in twenty minutes. CakeWorld Alpharetta.",
                call_ended=True, order_ready=True, order_type="pickup",
                tools_called=True, name="Priya")],
    )
    assert results[-1]["order_ready"] is False
    assert results[-1]["order"] is None


@pytest.mark.parametrize("bad", [
    'Sure. {"call_ended": false}',
    '{"answer": "hi"} trailing words',
    "no json at all",
])
def test_a_response_that_is_not_the_contract_cannot_be_constructed(bad):
    """The leak shape is rejected at the schema, so it never reaches a turn."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CallResponse.model_validate_json(bad)


def test_the_system_prompt_stays_small():
    """A ceiling so the prompt cannot re-grow one rule at a time.

    It reached 55,543 chars (~13,885 tokens, 45% of the request budget) by
    accretion, and that density is what made rules collide. If a change needs
    this raised, that is a decision to make deliberately, not by drift.
    """
    from prompts import SYSTEM_PROMPT

    assert len(SYSTEM_PROMPT) < 20_000, (
        f"system prompt is {len(SYSTEM_PROMPT)} chars "
        f"(~{len(SYSTEM_PROMPT) // 4} tokens); budget is 20,000"
    )


def test_history_budget_leaves_room_for_a_long_call():
    """The cut exists to buy history room; assert it actually did."""
    import config
    from context.assembler import assemble
    from prompts import SYSTEM_PROMPT

    history = [{"role": "user" if i % 2 == 0 else "assistant",
                "content": f"turn {i} " + "x" * 200} for i in range(200)]
    messages = assemble("next", history=history, domain="menu " * 800)
    kept = [m for m in messages if m.get("role") in ("user", "assistant")]

    assert len(SYSTEM_PROMPT) // 4 < 5_000
    # Before the cut this retained well under 100 turns.
    assert len(kept) > 120, f"only {len(kept)} turns survived assembly"
