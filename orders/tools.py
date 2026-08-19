"""Tools the model may call. Money arithmetic happens here, never in the LLM."""
import json

from menu.loader import find_item
from orders.calculator import calculate_order_total, price_order

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "price_order",
        "description": (
            "Price an order and compute subtotal, tax, and total. "
            "Always use this before quoting any price to the caller — "
            "never do the arithmetic yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Items the caller ordered.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Menu item name"},
                            "quantity": {"type": "integer", "description": "How many"},
                        },
                        "required": ["name", "quantity"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "lookup_item",
        "description": "Check whether a dish is on the menu and get its exact price.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
]


def run_tool(name: str, arguments: str | dict) -> str:
    args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
    if name == "price_order":
        return json.dumps(price_order(args.get("items", [])))
    if name == "lookup_item":
        found = find_item(args.get("name", ""))
        return json.dumps(found or {"error": "not on the menu"})
    return json.dumps({"error": f"unknown tool {name}"})
