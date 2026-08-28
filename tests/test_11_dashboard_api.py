"""Layer 11 — staff dashboard API.

Callers are identified by phone number (user_id). No login: the caller never
sees a screen. Staff read sessions grouped by caller.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    import api
    from providers.fake_provider import FakeProvider
    from storage.sqlite_store import SQLiteStore

    repo = SQLiteStore(str(tmp_path / "dash.db"))
    repo.init_db()
    api._repo, api._provider = repo, FakeProvider("order noted")
    yield TestClient(api.app)
    repo.close()
    api._repo = api._provider = None


def test_callers_endpoint_lists_distinct_phone_numbers(client):
    client.post("/chat", json={"user_id": "+919876543210", "message": "one dosa"})
    client.post("/chat", json={"user_id": "+919000000001", "message": "two idli"})
    callers = client.get("/callers").json()
    numbers = {c["user_id"] for c in callers}
    assert numbers == {"+919876543210", "+919000000001"}


def test_caller_row_has_session_and_message_counts(client):
    r = client.post("/chat", json={"user_id": "+911111111111", "message": "hi"})
    client.post("/chat", json={"user_id": "+911111111111",
                               "session_id": r.json()["session_id"], "message": "again"})
    caller = client.get("/callers").json()[0]
    assert caller["session_count"] == 1
    assert caller["message_count"] == 4


def test_sessions_include_message_count_and_timestamp(client):
    """Mirrors the Puerto Rico session-row shape: title + meta + counts."""
    client.post("/chat", json={"user_id": "+912222222222", "message": "paneer tikka"})
    s = client.get("/sessions", params={"user_id": "+912222222222"}).json()[0]
    assert s["message_count"] == 2
    assert s["updated_at"]
    assert s["title"]


def test_messages_include_timestamps_for_bubbles(client):
    sid = client.post("/chat", json={"user_id": "+913333333333",
                                     "message": "biryani"}).json()["session_id"]
    msgs = client.get(f"/sessions/{sid}/messages").json()
    assert all("created_at" in m and "role" in m for m in msgs)
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_search_sessions_returns_preview(client):
    client.post("/chat", json={"user_id": "+914444444444", "message": "extra spicy vindaloo"})
    hits = client.get("/search", params={"user_id": "+914444444444", "q": "vindaloo"}).json()
    assert hits and "vindaloo" in hits[0]["preview"].lower()


def test_staff_search_returns_matches_across_callers(client):
    client.post("/chat", json={"user_id": "+9141", "message": "extra spicy vindaloo"})
    client.post("/chat", json={"user_id": "+9142", "message": "vindaloo mild"})
    hits = client.get("/staff/search", params={"q": "vindaloo"}).json()
    assert {hit["user_id"] for hit in hits} == {"+9141", "+9142"}
    assert all(hit["session_id"] and hit["created_at"] for hit in hits)


def test_dashboard_page_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_phone_numbers_with_plus_are_matched(client):
    """A raw '+' in a query string decodes to a space; E.164 numbers must survive."""
    phone = "+919876543210"
    client.post("/chat", json={"user_id": phone, "message": "one biryani"})
    # unencoded '+' — exactly what curl and sloppy clients send
    assert len(client.get(f"/sessions?user_id={phone}").json()) == 1
    assert len(client.get("/sessions", params={"user_id": phone}).json()) == 1


def test_search_handles_plus_prefixed_numbers(client):
    phone = "+919000000009"
    client.post("/chat", json={"user_id": phone, "message": "mutton rogan josh"})
    hits = client.get(f"/search?user_id={phone}&q=mutton").json()
    assert hits


def _completed_order(client, phone="+915555555555", name="Anita", user_name=None):
    import api

    repo = api.get_repo()
    repo.ensure_user(phone)
    session = repo.create_session(phone, "pickup order")
    repo.append_message(session.session_id, "user", "one chilli paneer")
    repo.append_message(
        session.session_id,
        "assistant",
        "Your order is confirmed.",
        metadata={
            "order_ready": True,
            "order": {
                "customer_name": name,
                "fulfillment": "pickup",
                "items": [{
                    "name": "Chilli Paneer", "quantity": 1,
                    "unit_price": "11.99", "line_total": "11.99",
                }],
                "subtotal": "11.99", "tax": "0.93", "total": "12.92",
                "preparation_minutes": "20-30",
            },
            "response_fields": {
                "user_name": user_name or name,
                "name": name,
                "order_type": "pickup",
                "call_ended": True,
            },
        },
    )
    return session.session_id


def test_sessions_and_callers_use_structured_emitted_name(client):
    sid = _completed_order(client, name="Anita")
    assert client.get("/callers").json()[0]["name"] == "Anita"
    session = client.get("/sessions", params={"user_id": "+915555555555"}).json()[0]
    assert session["session_id"] == sid
    assert session["name"] == "Anita"
    assert session["order_type"] == "pickup"


def test_model_emitted_user_name_takes_precedence_for_caller_display(client):
    _completed_order(client, name="Office Reception", user_name="Anita")
    assert client.get("/callers").json()[0]["name"] == "Anita"
    session = client.get(
        "/sessions", params={"user_id": "+915555555555"}
    ).json()[0]
    assert session["name"] == "Anita"


def test_recent_orders_exposes_direct_chat_order(client):
    sid = _completed_order(client)
    orders = client.get("/orders/recent").json()["orders"]
    assert len(orders) == 1
    assert orders[0]["session_id"] == sid
    assert orders[0]["channel"] == "chat"
    assert orders[0]["order"]["total"] == "12.92"


def test_pickup_menu_is_read_only_and_omits_cake_and_catering(client):
    menu = client.get("/menu").json()
    assert menu["read_only"] is True
    assert menu["takeaway"]["item_count"] > 0
    assert menu["catering"]["item_count"] == 0
    assert menu["cakes"]["flavor_count"] == 0


def test_crm_is_aggregated_from_completed_sessions(client):
    sid = _completed_order(client, name="Anita")
    customers = client.get("/crm/customers").json()
    assert customers == [{
        "id": "+915555555555",
        "name": "Anita",
        "phone": "+915555555555",
        "orders": 1,
        "spend": 12.92,
        "last_order": customers[0]["last_order"],
        "diet": "",
        "address": "",
        "history": [{
            "type": "pickup",
            "id": sid,
            "status": "received",
            "pickup_time": "20-30",
            "total": 12.92,
            "created_at": customers[0]["history"][0]["created_at"],
            "items": [{"name": "Chilli Paneer", "qty": 1}],
        }],
    }]
