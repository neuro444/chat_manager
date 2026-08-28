"""Index the static menu in a Typesense collection."""

import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from menu.loader import menu_items
from storage.typesense_search import TypesenseSearch, TypesenseConfig


MENU_FIELDS = [
    {"name": "id", "type": "string"},
    {"name": "name", "type": "string"},
    {"name": "category", "type": "string", "facet": True},
    {"name": "price", "type": "float"},
    {"name": "is_vegetarian", "type": "bool", "facet": True},
]


def build_search() -> TypesenseSearch:
    base_config = TypesenseConfig.from_environment()
    config = TypesenseConfig(
        url=base_config.url,
        api_key=base_config.api_key,
        collection=os.getenv("TYPESENSE_MENU_COLLECTION", "menu"),
    )
    return TypesenseSearch(config)


def ensure_collection(search: TypesenseSearch) -> None:
    response = search.client.get(f"/collections/{search.config.collection}")
    if response.status_code == 404:
        response = search.client.post(
            "/collections",
            json={
                "name": search.config.collection,
                "fields": MENU_FIELDS,
            },
        )
    response.raise_for_status()


def main() -> None:
    search = build_search()
    try:
        ensure_collection(search)
        count = 0
        for item in menu_items():
            document = {
                "id": item["name"].strip().lower().replace(" ", "-"),
                "name": item["name"],
                "category": item["category"],
                "price": float(item["price"]),
                "is_vegetarian": bool(item["is_vegetarian"]),
            }
            response = search.client.post(
                f"/collections/{search.config.collection}/documents?action=upsert",
                json=document,
            )
            response.raise_for_status()
            count += 1
            print(f"Indexed {count}: {document['name']}")

        print(f"Total indexed: {count}")
    finally:
        search.client.close()


if __name__ == "__main__":
    main()
