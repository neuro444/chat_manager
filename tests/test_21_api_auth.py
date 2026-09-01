"""Layer 21 — API key auth.

Two named keys, not one shared secret: the telephony gateway calls /chat
across the network, and staff tooling (this repo's own bundled dashboard,
and voice_central) calls /chat plus every transcript/session/order route.
These tests pin the whole contract: each key works where it should, the
telephony key is specifically rejected on dashboard-only routes (the actual
point of splitting the keys), and auth stays invisible when both are unset.
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
    """Both keys set -- the normal production shape."""
    monkeypatch.setattr(config, "TELEPHONY_API_KEY", "t3l3phony")
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "d4shboard")
    return {
        "telephony": {"X-API-Key": "t3l3phony"},
        "dashboard": {"X-API-Key": "d4shboard"},
    }


# Every route that returns caller data, other than /chat -- dashboard key
# only. /health is deliberately absent (Docker's healthcheck and the
# gateway's readiness probe need it open with no key at all).
GUARDED = [
    ("get", "/callers"),
    ("get", "/sessions?user_id=%2B15551234567"),
    ("get", "/search?user_id=%2B15551234567&q=samosa"),
    ("get", "/staff/search?q=samosa"),
    ("get", "/orders/recent"),
    ("get", "/menu"),
    ("get", "/crm/customers"),
]


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_rejects_missing_key(client, keyed, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_rejects_wrong_key(client, keyed, method, path):
    r = getattr(client, method)(path, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_accepts_dashboard_key(client, keyed, method, path):
    r = getattr(client, method)(path, headers=keyed["dashboard"])
    assert r.status_code == 200


@pytest.mark.parametrize("method,path", GUARDED)
def test_guarded_route_rejects_telephony_key(client, keyed, method, path):
    """The point of splitting the keys: telephony has no reason to be here."""
    r = getattr(client, method)(path, headers=keyed["telephony"])
    assert r.status_code == 401


def test_chat_rejects_missing_key(client, keyed):
    body = {"user_id": "+15551234567", "message": "hi"}
    assert client.post("/chat", json=body).status_code == 401


def test_chat_accepts_telephony_key(client, keyed):
    body = {"user_id": "+15551234567", "message": "hi"}
    r = client.post("/chat", json=body, headers=keyed["telephony"])
    assert r.status_code == 200


def test_chat_accepts_dashboard_key(client, keyed):
    """The dashboard's own live chat-test feature calls /chat too."""
    body = {"user_id": "+15551234567", "message": "hi"}
    r = client.post("/chat", json=body, headers=keyed["dashboard"])
    assert r.status_code == 200


def test_chat_rejects_wrong_key(client, keyed):
    body = {"user_id": "+15551234567", "message": "hi"}
    r = client.post("/chat", json=body, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_health_never_requires_key(client, keyed):
    """The gateway and Docker probe /health before they have any credentials."""
    assert client.get("/health").status_code == 200


def test_auth_disabled_when_both_keys_unset(client, monkeypatch):
    """Both keys unset means local dev and the existing suite are unaffected."""
    monkeypatch.setattr(config, "TELEPHONY_API_KEY", "")
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "")
    assert client.get("/callers").status_code == 200
    assert client.post(
        "/chat", json={"user_id": "+15551234567", "message": "hi"}
    ).status_code == 200


def test_startup_check_warns_when_telephony_key_unset(caplog, monkeypatch):
    import api
    import logging
    monkeypatch.setattr(config, "TELEPHONY_API_KEY", "")
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "d4shboard")
    with caplog.at_level(logging.WARNING):
        is_enabled = api.check_api_key_configuration()
        assert not is_enabled
        assert any("TELEPHONY_API_KEY is not set" in record.message for record in caplog.records)


def test_startup_check_warns_when_dashboard_key_unset(caplog, monkeypatch):
    import api
    import logging
    monkeypatch.setattr(config, "TELEPHONY_API_KEY", "t3l3phony")
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "")
    with caplog.at_level(logging.WARNING):
        is_enabled = api.check_api_key_configuration()
        assert not is_enabled
        assert any("DASHBOARD_API_KEY is not set" in record.message for record in caplog.records)


def test_startup_check_logs_info_when_both_keys_set(caplog, monkeypatch):
    import api
    import logging
    monkeypatch.setattr(config, "TELEPHONY_API_KEY", "t3l3phony")
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "d4shboard")
    with caplog.at_level(logging.INFO):
        is_enabled = api.check_api_key_configuration()
        assert is_enabled
        assert any("API key authentication is ENABLED" in record.message for record in caplog.records)


def test_dashboard_route_disabled_when_only_telephony_key_set(client, monkeypatch):
    """Partial config: DASHBOARD_API_KEY unset disables its own guard, same
    no-op behavior as the fully-unset case -- not an accidental telephony-key
    bypass onto dashboard routes."""
    monkeypatch.setattr(config, "TELEPHONY_API_KEY", "t3l3phony")
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "")
    assert client.get("/callers").status_code == 200
    r = client.get("/callers", headers={"X-API-Key": "t3l3phony"})
    assert r.status_code == 200  # no-op guard accepts everything, not just this key
