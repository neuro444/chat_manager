"""Best-effort Typesense search support for chat messages."""

import logging
import os
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)


class TypesenseError(RuntimeError):
    """Base error for Typesense search failures."""


class TypesenseNotConfigured(TypesenseError):
    """Raised when required Typesense configuration is missing."""


class TypesenseUnavailable(TypesenseError):
    """Raised when Typesense cannot complete a search."""


@dataclass(frozen=True)
class TypesenseConfig:
    url: str
    api_key: str
    collection: str

    @classmethod
    def from_environment(cls) -> "TypesenseConfig":
        url = os.getenv("TYPESENSE_URL", "").rstrip("/")
        api_key = os.getenv("TYPESENSE_API_KEY", "")
        collection = os.getenv("TYPESENSE_COLLECTION", "chat_messages")
        if not url or not api_key:
            raise TypesenseNotConfigured(
                "TYPESENSE_URL and TYPESENSE_API_KEY must be configured"
            )
        return cls(url=url, api_key=api_key, collection=collection)


COLLECTION_FIELDS = [
    {"name": "message_id", "type": "string"},
    {"name": "session_id", "type": "string"},
    {"name": "user_id", "type": "string", "facet": True},
    {"name": "role", "type": "string", "facet": True},
    {"name": "content", "type": "string"},
    {"name": "created_at", "type": "int64", "sort": True},
]


class TypesenseSearch:
    def __init__(self, config: TypesenseConfig):
        self.config = config
        self.client = httpx.Client(
            base_url=config.url,
            headers={"X-TYPESENSE-API-KEY": config.api_key},
            timeout=5.0,
        )
        self._ready = False

    def _ensure_collection(self) -> None:
        if self._ready:
            return

        response = self.client.get(f"/collections/{self.config.collection}")
        if response.status_code == 404:
            response = self.client.post(
                "/collections",
                json={
                    "name": self.config.collection,
                    "fields": COLLECTION_FIELDS,
                    "default_sorting_field": "created_at",
                },
            )
        response.raise_for_status()
        self._ready = True

    def index_message(self, doc: dict) -> None:
        try:
            self._ensure_collection()
            response = self.client.post(
                f"/collections/{self.config.collection}/documents?action=upsert",
                json=doc,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("Typesense message indexing failed: %s", exc)

    def search_message_ids(self, user_id: str, query: str, limit: int) -> list[str]:
        try:
            self._ensure_collection()
            response = self.client.get(
                f"/collections/{self.config.collection}/documents/search",
                params={
                    "q": query,
                    "query_by": "content",
                    "filter_by": f"user_id:={user_id} && role:=user" if user_id else "role:=user",
                    "per_page": limit,
                    "num_typos": 2,
                    "prefix": True,
                },
            )
            response.raise_for_status()
            return [
                hit["document"]["message_id"]
                for hit in response.json().get("hits", [])
            ]
        except Exception as exc:
            raise TypesenseUnavailable("Typesense search failed") from exc


def get_search() -> "TypesenseSearch":
    """Build a fresh service each call. Raises TypesenseNotConfigured if env is unset."""
    return TypesenseSearch(TypesenseConfig.from_environment())
