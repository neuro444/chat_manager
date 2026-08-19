"""Order arithmetic.

LLMs are unreliable at multi-step money arithmetic, so totals are computed in
code and handed to the model as fact rather than asked for.
"""

TAX_RATE = 0.0775  # 7.75%


def calculate_order_total(items: list[dict], tax_rate: float = TAX_RATE) -> dict:
    """items: [{"price": 12.99, "quantity": 2}, ...]"""
    for item in items:
        if item.get("quantity", 1) < 0:
            raise ValueError(f"negative quantity: {item}")
        if item.get("price", 0) < 0:
            raise ValueError(f"negative price: {item}")

    subtotal = round(
        sum(item["price"] * item.get("quantity", 1) for item in items), 2
    )
    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax, 2)
    return {"subtotal": subtotal, "tax_rate": tax_rate, "tax": tax, "total": total}


def price_order(named_items: list[dict]) -> dict:
    """Resolve names against the menu, then total.

    named_items: [{"name": "Samosa", "quantity": 2}, ...]
    Returns the priced lines, any unmatched names, and the totals.
    """
    from menu.loader import find_item

    lines, unknown = [], []
    for entry in named_items:
        found = find_item(entry.get("name", ""))
        if not found:
            unknown.append(entry.get("name", ""))
            continue
        qty = entry.get("quantity", 1)
        lines.append({
            "name": found["name"], "price": found["price"], "quantity": qty,
            "line_total": round(found["price"] * qty, 2),
        })
    totals = calculate_order_total(lines)
    return {"items": lines, "unknown": unknown, **totals}


def format_totals_for_speech(totals: dict) -> str:
    """Phone-friendly phrasing — the agent reads this aloud."""
    return (f"subtotal ${totals['subtotal']:.2f}, "
            f"tax ${totals['tax']:.2f}, "
            f"total ${totals['total']:.2f}")
