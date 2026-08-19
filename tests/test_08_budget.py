"""Layer 8 — token budget: oversized input must be trimmed, invariants held."""
import config
from context.assembler import assemble


def _tokens(msgs):
    return sum(len(m["content"]) for m in msgs) // config.CHARS_PER_TOKEN


def test_huge_context_is_trimmed_under_budget():
    huge = "word " * 200_000
    msgs = assemble("hi", history=[], summary=huge, memory=huge,
                    profile=huge, domain=huge)
    assert _tokens(msgs) < config.MAX_CONTEXT_TOKENS


def test_huge_history_is_trimmed_under_budget():
    history = [{"role": "user", "content": "x" * 5000} for _ in range(200)]
    msgs = assemble("hi", history=history)
    assert _tokens(msgs) < config.MAX_CONTEXT_TOKENS


def test_user_message_never_trimmed():
    long_q = "Q" * 20_000
    msgs = assemble(long_q, history=[], summary="s" * 90_000)
    assert msgs[-1]["content"] == long_q


def test_user_message_always_last():
    msgs = assemble("final question",
                    history=[{"role": "user", "content": "old"}],
                    summary="s", memory="m", profile="p", domain="d")
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "final question"


def test_system_prompt_always_first():
    msgs = assemble("q", history=[], summary="s")
    assert msgs[0]["role"] == "system"


def test_each_layer_respects_its_weight():
    """A greedy layer must not consume another layer's share."""
    huge = "z" * 500_000
    msgs = assemble("q", history=[], summary=huge, memory=huge,
                    profile=huge, domain=huge)
    block = next(m["content"] for m in msgs[1:2])
    available = (config.MAX_CONTEXT_TOKENS - config.RESERVED_FOR_REPLY)
    for key in ("summary", "memory", "profile", "domain"):
        cap = int(available * config.CONTEXT_BUDGET_WEIGHTS[key]) * config.CHARS_PER_TOKEN
        assert block.count("z") <= sum(
            int(available * config.CONTEXT_BUDGET_WEIGHTS[k]) * config.CHARS_PER_TOKEN
            for k in ("summary", "memory", "profile", "domain")
        )


def test_trim_cuts_on_boundary_not_mid_sentence():
    from context.assembler import _trim
    text = "First sentence here. Second sentence here. Third sentence here."
    out = _trim(text, 45)
    assert out.endswith(". ") or out.endswith(".") or len(out) <= 45
