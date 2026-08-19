"""Layer 16 — the pricing tool is actually invoked.

Asserting only that a total is correct is too weak: the model could do the
arithmetic itself and happen to be right. These tests assert the tool ran.
"""
import json

import pytest

from orders.tools import TOOL_SCHEMAS, run_tool


class ToolCallingProvider:
    """Fake that emits a tool call, then answers from the tool's result.

    Mirrors the real two-step Responses flow without a network call.
    """

    def __init__(self):
        self.tool_calls = []
        self.saw_tool_output = False

    def complete(self, messages, tools=None, **kw):
        if not tools:
            return "no tools offered"
        names = {t["name"] for t in tools}
        assert "price_order" in names

        # step 1: the model decides to price the order
        args = json.dumps({"items": [{"name": "Samosa", "quantity": 2},
                                     {"name": "Gobi Manchurian", "quantity": 1}]})
        result = run_tool("price_order", args)
        self.tool_calls.append(("price_order", args, result))

        # step 2: it answers using what the tool returned
        totals = json.loads(result)
        self.saw_tool_output = True
        return f"Your total is {totals['total']}."

    def stream(self, messages, **kw):
        yield self.complete(messages)

    def count_tokens(self, text):
        return len(text) // 4


def test_tool_schemas_are_well_formed():
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert schema["name"] and schema["description"]
        params = schema["parameters"]
        assert params["type"] == "object"
        for req in params["required"]:
            assert req in params["properties"], f"{schema['name']}: {req} not defined"


def test_price_order_tool_returns_correct_totals():
    out = json.loads(run_tool("price_order", json.dumps(
        {"items": [{"name": "Samosa", "quantity": 2},
                   {"name": "Gobi Manchurian", "quantity": 1}]})))
    assert out["subtotal"] == 23.97
    assert out["tax"] == 1.86
    assert out["total"] == 25.83


def test_lookup_item_tool():
    out = json.loads(run_tool("lookup_item", json.dumps({"name": "Samosa"})))
    assert out["price"] == 5.99


def test_unknown_item_is_reported_not_invented():
    out = json.loads(run_tool("price_order", json.dumps(
        {"items": [{"name": "Wagyu Steak", "quantity": 1}]})))
    assert out["unknown"] == ["Wagyu Steak"]
    assert out["items"] == []


def test_unknown_tool_name_is_handled():
    assert "error" in json.loads(run_tool("nonexistent", "{}"))


def test_service_offers_tools_to_the_provider(repo):
    """The pipeline must actually pass TOOL_SCHEMAS through to the provider."""
    from service import handle_message
    provider = ToolCallingProvider()
    handle_message(repo, provider, "+9199", None, "two samosas and a gobi manchurian")
    assert provider.tool_calls, "price_order was never offered/called"
    assert provider.saw_tool_output


def test_answer_is_derived_from_tool_result(repo):
    from service import handle_message
    provider = ToolCallingProvider()
    out = handle_message(repo, provider, "+9199", None, "two samosas and a gobi manchurian")
    assert "25.83" in out["answer"]


def test_provider_without_tool_support_still_works(repo):
    """Fallback path: a provider whose complete() takes no `tools` kwarg."""
    from providers.fake_provider import FakeProvider
    from service import handle_message
    out = handle_message(repo, FakeProvider("plain"), "+9199", None, "hi")
    assert out["answer"] == "plain"
