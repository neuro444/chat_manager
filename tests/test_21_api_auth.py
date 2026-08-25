"""Layer 21 — API key auth.

The telephony gateway calls /chat across the network, so the API is no longer
purely local. These tests pin both halves of the contract: the key is enforced
when set, and auth stays invisible when it is not.
"""
import pytest
from fastapi.testclient import TestClient

import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api
    from providers.fake_provider import FakeProvider
    from storage.sqlite_store import SQLiteStore

    repo = SQLiteStore(str(tmp_path / "auth.db"))
    repo.init_db()
    api._repo = repo
    api._provider = FakeProvider("api reply")
    yield TestClient(api.app)
    repo.close()
    api._repo = api._provider = None


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "s3cret")
    return {"X-API-Key": "s3cret"}


# Every route that returns caller data or costs money to call. /health is
# deliberately absent — Docker's healthcheck and the gateway probe need it open.
GUARDED = [
    ("get", "/callers"),
    ("get", "/sessions?user_id=%2B15551234567"),
    ("get", "/search?user_id=%2B15551234567&q=samosa"),
    ("get", "/staff/search?q=samosa"),
]


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_rejects_missing_key(client, keyed, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_rejects_wrong_key(client, keyed, method, path):
    r = getattr(client, method)(path, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_accepts_correct_key(client, keyed, method, path):
    assert getattr(client, method)(path, headers=keyed).status_code == 200


def test_chat_requires_key(client, keyed):
    body = {"user_id": "+15551234567", "message": "hi"}
    assert client.post("/chat", json=body).status_code == 401
    assert client.post("/chat", json=body, headers=keyed).status_code == 200


def test_health_never_requires_key(client, keyed):
    """The gateway and Docker probe /health before they have any credentials."""
    assert client.get("/health").status_code == 200


def test_auth_disabled_when_key_unset(client, monkeypatch):
    """Unset key means local dev and the existing suite are unaffected."""
    monkeypatch.setattr(config, "API_KEY", "")
    assert client.get("/callers").status_code == 200
    assert client.post(
        "/chat", json={"user_id": "+15551234567", "message": "hi"}
    ).status_code == 200
