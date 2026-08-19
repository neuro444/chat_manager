"""Menu loading and prompt rendering.

Source of truth is `menu_flat.json`: a field header plus one row-array per item,
which is far smaller than repeating keys on every record.

What the model sees is CSV, not JSON — no braces, quotes, or repeated field
names, so the same 153 items cost roughly a fifth of the tokens.
"""
import csv
import io
import json
from functools import lru_cache
from pathlib import Path

MENU_PATH = Path(__file__).parent / "menu_flat.json"


@lru_cache(maxsize=1)
def load_menu(path: str | None = None) -> dict:
    """Return the raw flat menu document."""
    return json.loads(Path(path or MENU_PATH).read_text())


@lru_cache(maxsize=1)
def menu_items(path: str | None = None) -> tuple[dict, ...]:
    """Row arrays zipped back into dicts, using the declared field header."""
    doc = load_menu(path)
    fields = doc["menu_item_fields"]
    return tuple(dict(zip(fields, row)) for row in doc["menu_items"])


@lru_cache(maxsize=1)
def format_menu_for_prompt(path: str | None = None) -> str:
    """Render the menu as CSV for the prompt."""
    doc = load_menu(path)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["name", "price", "category", "veg"])
    for item in menu_items(path):
        writer.writerow([
            item["name"],
            f"{item['price']:.2f}",
            item["category"],
            "yes" if item.get("is_vegetarian") else "no",
        ])

    header = (
        f"{doc.get('restaurant_name', 'Restaurant')} — {doc.get('cuisine', '')}"
    ).strip(" —")
    parts = [header, "", "MENU (CSV, prices in dollars):", buf.getvalue().rstrip()]

    flavours = doc.get("cake_flavours") or []
    names = [f if isinstance(f, str) else f.get("name", "") for f in flavours]
    names = [n for n in names if n]
    if names:
        parts += ["", "Cake flavours: " + ", ".join(names)]

    return "\n".join(parts)


def find_item(name: str, path: str | None = None) -> dict | None:
    """Look an item up by name — exact first, then case-insensitive substring."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    items = menu_items(path)
    for i in items:
        if i["name"].lower() == needle:
            return i
    for i in items:
        if needle in i["name"].lower() or i["name"].lower() in needle:
            return i
    return None
