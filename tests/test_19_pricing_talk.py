"""Layer 19 — pricing conversation rules.

Menu prices while discussing items; the tool only at the final review, where
unit prices are read back before the total.
"""
from prompts import SYSTEM_PROMPT


def test_prompt_says_quote_menu_price_while_discussing():
    p = SYSTEM_PROMPT.lower()
    assert "menu price" in p
    assert "lookup_item" in SYSTEM_PROMPT


def test_prompt_defers_price_order_to_the_final_review():
    p = SYSTEM_PROMPT.lower()
    assert "final" in p and "price_order" in SYSTEM_PROMPT


def test_prompt_separates_fulfillment_from_food_selection():
    p = SYSTEM_PROMPT.lower()
    assert "never combine a menu question" in p
    assert "wait" in p and "food selection" in p


def test_prompt_defaults_pickup_readiness_and_routes_large_orders():
    p = SYSTEM_PROMPT.lower()
    assert "twenty to thirty minutes" in p
    assert "regular pickup order or catering" in p


def test_prompt_contains_business_hours_and_closed_order_timing():
    p = " ".join(SYSTEM_PROMPT.lower().split())
    assert "sunday through saturday" in p
    assert "11:00 am to 11:00 pm" in p
    assert "missing current-time context alone is not a reason" in p
    assert "do not add an hours question" in p
    assert "if it shows the restaurant is closed" in p
    assert "processed when the restaurant opens" in p
    assert "twenty to thirty minutes after preparation starts" in p
    assert "hours-only conversation has call_ended=true" in p


def test_prompt_has_one_review_and_small_orders_do_not_trigger_catering():
    p = " ".join(SYSTEM_PROMPT.lower().split())
    assert "once the caller answers that review, never ask an equivalent" in p
    assert "fulfillment does not reset it" in p
    assert "small-group order does not become catering" in p
    assert "five chicken fried rice and three porottas" in p
    assert "does not introduce business hours" in p
    assert "fulfillment does not repeat the pickup review" in p
    assert "three kandari chicken fry" in p


def test_prompt_reads_large_totals_as_thousands_and_dollars():
    p = " ".join(SYSTEM_PROMPT.lower().split())
    assert "total of one thousand dollars or more" in p
    assert "one thousand seven hundred twenty-two dollars and ninety-two cents" in p
    assert "seventeen twenty-two ninety-two" in p


def test_prompt_requires_unit_prices_in_the_readback():
    assert "unit price" in SYSTEM_PROMPT.lower()


def test_prompt_makes_tax_inclusive_total_clear_without_breakdown():
    p = SYSTEM_PROMPT.lower()
    assert "total, including tax" in p
    assert "do not read the separate tax" in p


def test_price_order_still_returns_line_items_for_the_readback():
    """The readback needs per-item unit prices, not just a total."""
    from orders.calculator import price_order
    out = price_order([{"name": "Samosa", "quantity": 2},
                       {"name": "Malabar Chicken Biriyani", "quantity": 1}])
    assert [i["price"] for i in out["items"]] == [5.99, 15.99]
    assert out["items"][0]["line_total"] == 11.98
    assert out["subtotal"] == 27.97
    assert out["total"] == 30.14


def test_lookup_item_gives_the_untaxed_menu_price():
    from menu.loader import find_item
    assert find_item("Malabar Chicken Biriyani")["price"] == 15.99
