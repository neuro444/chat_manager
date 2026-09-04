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
    monkeypatch.setattr(config, "API_KEY", "s3cret")
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


def test_breakdown_path_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream(monkeypatch, content=b'{"group_by":"day","periods":[]}')
    resp = client.get("/cost/api/internal/costs/breakdown", headers=keyed,
                       params={"group_by": "day"})
    assert resp.status_code == 200
    assert resp.json()["group_by"] == "day"


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


def _mock_upstream_request(monkeypatch, *, content=b'{"ok":true}', status_code=200, captured=None):
    # Named response_content, not content: content is also the kwarg
    # _forward_write passes for the *request* body, and a same-named inner
    # parameter would shadow this closure's response body with that instead.
    async def fake_request(self, method, url, content=None, params=None, headers=None, **kwargs):
        if captured is not None:
            captured["params"] = params
        return httpx.Response(status_code, content=response_content, request=httpx.Request(method, url))

    response_content = content
    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)


def test_price_book_list_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream_request(monkeypatch, content=b'{"rates":[]}')
    resp = client.get("/cost/api-write/price-book", headers=keyed)
    assert resp.status_code == 200
    assert resp.json() == {"rates": []}


def test_price_book_list_forwards_query_params(client, keyed, monkeypatch):
    # Regression test: _forward_write initially built the upstream request
    # with no `params=`, so ?include_history=true silently vanished and the
    # Rates tab's "Show history" toggle looked broken (pending/superseded
    # rows never appeared) even though the write itself succeeded.
    captured = {}
    _mock_upstream_request(monkeypatch, content=b'{"rates":[]}', captured=captured)
    resp = client.get("/cost/api-write/price-book", headers=keyed,
                       params={"include_history": "true", "provider": "openai"})
    assert resp.status_code == 200
    assert captured["params"] == {"include_history": "true", "provider": "openai"}


def test_price_book_create_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream_request(monkeypatch, content=b'{"id":1,"approval_status":"pending"}')
    resp = client.post("/cost/api-write/price-book", headers=keyed, json={
        "provider": "openai", "model": "gpt-x", "billing_unit": "minute", "flat_rate": "0.01",
    })
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "pending"


def test_price_book_approve_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream_request(monkeypatch, content=b'{"id":1,"approval_status":"approved"}')
    resp = client.patch("/cost/api-write/price-book/1/approve", headers=keyed)
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "approved"


def test_price_book_reject_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream_request(monkeypatch, content=b'{"id":1,"approval_status":"rejected"}')
    resp = client.patch("/cost/api-write/price-book/1/reject", headers=keyed, json={})
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "rejected"


def test_price_book_deactivate_is_forwarded(client, keyed, monkeypatch):
    _mock_upstream_request(monkeypatch, content=b'{"id":1,"effective_to":"2026-09-04T00:00:00Z"}')
    resp = client.post("/cost/api-write/price-book/1/deactivate", headers=keyed)
    assert resp.status_code == 200
    assert resp.json()["effective_to"] is not None


def test_price_book_create_requires_key(client, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "s3cret")
    resp = client.post("/cost/api-write/price-book", json={})
    assert resp.status_code == 401


def test_price_book_write_unreachable_returns_503(client, keyed, monkeypatch):
    async def fake_request(self, method, url, content=None, headers=None, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    resp = client.post("/cost/api-write/price-book", headers=keyed, json={})
    assert resp.status_code == 503
