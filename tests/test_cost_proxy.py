"""Cost monitor proxy — GET-only, allowlisted paths, forwards to cost-api.

Upstream cost-api is never actually called here: httpx.AsyncClient.get is
monkeypatched so these tests stay fast and don't need a real cost-api or
Postgres running."""
import httpx
import pytest
from fastapi.testclient import TestClient

import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api
    from providers.fake_provider import FakeProvider
    from storage.sqlite_store import SQLiteStore

    repo = SQLiteStore(str(tmp_path / "cost_proxy.db"))
    repo.init_db()
    api._repo = repo
    api._provider = FakeProvider("api reply")
    yield TestClient(api.app)
    repo.close()
    api._repo = api._provider = None


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(config, "DASHBOARD_API_KEY", "s3cret")
    return {"X-API-Key": "s3cret"}


def _mock_upstream(monkeypatch, *, content=b'{"ok":true}', status_code=200):
    async def fake_get(self, url, params=None, **kwargs):
        return httpx.Response(status_code, content=content, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


def test_allowed_path_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream(monkeypatch, content=b'{"date":"2026-09-04","total_cost_usd":"1.23"}')
    resp = client.get("/cost/api/internal/costs/daily", headers=keyed)
    assert resp.status_code == 200
    assert resp.json()["total_cost_usd"] == "1.23"


def test_call_drilldown_path_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream(monkeypatch, content=b'{"call_id":"abc"}')
    resp = client.get("/cost/api/internal/calls/abc", headers=keyed)
    assert resp.status_code == 200
    assert resp.json()["call_id"] == "abc"


def test_disallowed_path_returns_404(client, keyed, monkeypatch):
    _mock_upstream(monkeypatch)
    resp = client.get("/cost/api/internal/cost-events", headers=keyed)
    assert resp.status_code == 404


def test_missing_key_is_rejected(client, keyed):
    resp = client.get("/cost/api/internal/costs/daily")
    assert resp.status_code == 401


def test_upstream_unreachable_returns_503(client, keyed, monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    resp = client.get("/cost/api/internal/costs/daily", headers=keyed)
    assert resp.status_code == 503


def test_post_is_not_allowed(client, keyed, monkeypatch):
    _mock_upstream(monkeypatch)
    resp = client.post("/cost/api/internal/reviews/run", headers=keyed)
    assert resp.status_code == 405


def test_pin_check_not_required_when_unset(client, keyed, monkeypatch):
    monkeypatch.setattr(config, "COST_MONITOR_PIN", "")
    resp = client.get("/cost/pin-check", headers=keyed)
    assert resp.status_code == 200
    assert resp.json() == {"pin_required": False, "correct": True}


def test_pin_check_rejects_wrong_pin(client, keyed, monkeypatch):
    monkeypatch.setattr(config, "COST_MONITOR_PIN", "4080")
    resp = client.get("/cost/pin-check", params={"pin": "0000"}, headers=keyed)
    assert resp.status_code == 200
    assert resp.json() == {"pin_required": True, "correct": False}


def test_pin_check_accepts_correct_pin(client, keyed, monkeypatch):
    monkeypatch.setattr(config, "COST_MONITOR_PIN", "4080")
    resp = client.get("/cost/pin-check", params={"pin": "4080"}, headers=keyed)
    assert resp.status_code == 200
    assert resp.json() == {"pin_required": True, "correct": True}
