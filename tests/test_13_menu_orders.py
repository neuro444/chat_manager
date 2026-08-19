"""Layer 13 — menu, order calculator, caller names, session expiry."""
import json
import pytest

from menu.loader import format_menu_for_prompt, find_item, load_menu, menu_items
from orders.calculator import calculate_order_total


# ── calculator ───────────────────────────
def test_calculator_matches_spec_example():
    r = calculate_order_total([{"price": 12.99, "quantity": 2},
                               {"price": 5.99, "quantity": 1}])
    assert r == {"subtotal": 31.97, "tax_rate": 0.0775, "tax": 2.48, "total": 34.45}


def test_calculator_empty_order():
    r = calculate_order_total([])
    assert r["subtotal"] == 0 and r["total"] == 0


def test_calculator_rounds_to_cents():
    r = calculate_order_total([{"price": 10.333, "quantity": 3}])
    assert r["subtotal"] == round(r["subtotal"], 2)
    assert r["total"] == round(r["subtotal"] + r["tax"], 2)


def test_calculator_defaults_quantity_to_one():
    assert calculate_order_total([{"price": 5.00}])["subtotal"] == 5.00


def test_calculator_rejects_negative_quantity():
    with pytest.raises(ValueError):
        calculate_order_total([{"price": 5.00, "quantity": -1}])


# ── menu ─────────────────────────────────
def test_menu_loads_all_items():
    assert len(menu_items()) == 153


def test_flat_rows_zip_against_declared_fields():
    """Row arrays are positional; a header/row mismatch would corrupt prices."""
    doc = load_menu()
    fields = doc["menu_item_fields"]
    assert fields == ["name", "price", "category", "is_vegetarian"]
    assert all(len(row) == len(fields) for row in doc["menu_items"])
    first = menu_items()[0]
    assert isinstance(first["name"], str) and isinstance(first["price"], (int, float))


def test_menu_is_sent_as_csv_not_json():
    text = format_menu_for_prompt()
    assert "name,price,category,veg" in text
    assert "{" not in text and "}" not in text


def test_menu_prompt_fits_budget():
    """Raw JSON is ~5k tokens and would be truncated; compact form must fit."""
    import config
    text = format_menu_for_prompt()
    budget = int((config.MAX_CONTEXT_TOKENS - config.RESERVED_FOR_REPLY)
                 * config.CONTEXT_BUDGET_WEIGHTS["domain"])
    assert len(text) // config.CHARS_PER_TOKEN < budget


def test_menu_prompt_contains_every_item_and_price():
    text = format_menu_for_prompt()
    for item in menu_items():
        assert item["name"] in text
        assert f"{item['price']:.2f}" in text


def test_find_item_exact_and_fuzzy():
    assert find_item("Samosa")["price"] == 5.99
    assert find_item("samosa")["price"] == 5.99
    assert find_item("gobi manchurian")["price"] == 11.99
    assert find_item("nonexistent dish") is None


# ── caller names ─────────────────────────
def test_caller_name_is_stored_and_reused(repo):
    from providers.fake_provider import FakeProvider
    from service import build_context, handle_message
    repo.set_user_name("+919876543210", "Sree")
    handle_message(repo, FakeProvider(), "+919876543210", None, "one samosa")
    sid = repo.list_sessions("+919876543210")[0].session_id
    blob = "\n".join(m["content"] for m in
                     build_context(repo, "+919876543210", sid, "hi"))
    assert "Sree" in blob


def test_name_extracted_from_conversation(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message
    handle_message(repo, FakeProvider(), "+911111111111", None,
                   "Hi, this is Priya, I'd like a dosa")
    assert repo.get_user("+911111111111").name == "Priya"


# ── session expiry ───────────────────────
def test_expired_session_starts_fresh(repo):
    from datetime import datetime, timedelta, timezone
    from providers.fake_provider import FakeProvider
    from service import handle_message

    out = handle_message(repo, FakeProvider(), "+912222222222", None, "one naan")
    sid = out["session_id"]
    # age the session past the timeout
    repo.sessions[sid].updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    out2 = handle_message(repo, FakeProvider(), "+912222222222", None, "another call")
    assert out2["session_id"] != sid, "a call after the timeout must start a new session"


def test_recent_session_is_resumed(repo):
    from providers.fake_provider import FakeProvider
    from service import handle_message
    out = handle_message(repo, FakeProvider(), "+913333333333", None, "one naan")
    out2 = handle_message(repo, FakeProvider(), "+913333333333", out["session_id"],
                          "and a lassi")
    assert out2["session_id"] == out["session_id"]


@pytest.mark.parametrize("text,expected", [
    ("This is Priya, two samosas please", "Priya"),      # sentence-initial
    ("Hi, this is Priya. What do you have?", "Priya"),   # mid-sentence
    ("this is priya calling", "Priya"),                  # all lowercase
    ("My name is Arjun", "Arjun"),
    ("I'm Deepa", "Deepa"),
    ("Hi, I'd like two samosas", None),                  # no name present
    ("I'm looking for the menu", None),                  # verb, not a name
    ("This is for pickup", None),                        # not a name
])
def test_name_extraction_variants(text, expected):
    from context.caller import extract_name
    assert extract_name(text) == expected
