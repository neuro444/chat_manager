"""Layer 10 — HTTP API. Same engine, exercised over HTTP."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api
    from providers.fake_provider import FakeProvider
    from storage.sqlite_store import SQLiteStore

    repo = SQLiteStore(str(tmp_path / "api.db"))
    repo.init_db()
    api._repo = repo
    api._provider = FakeProvider("api reply")
    yield TestClient(api.app)
    repo.close()
    api._repo = api._provider = None


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_chat_returns_reply_and_session(client):
    r = client.post("/chat", json={"user_id": "u1", "message": "hello"})
    assert r.status_code == 200
    assert r.json()["answer"] == "api reply"
    assert r.json()["session_id"]
    assert "llm_debug" not in r.json()


def test_chat_can_return_llm_debug_for_dashboard(client):
    r = client.post("/chat", json={
        "user_id": "u1",
        "message": "hello",
        "include_llm_debug": True,
    })
    assert r.status_code == 200
    debug = r.json()["llm_debug"]
    assert debug["output"] == "api reply"
    assert debug["latest_query"] == "hello"
    assert debug["combined_input"][-1] == {"role": "user", "content": "hello"}
    assert "Reference data" not in debug["reference_data"]
    assert debug["system_prompt"]


def test_chat_continues_session(client):
    sid = client.post("/chat", json={"user_id": "u1", "message": "first"}).json()["session_id"]
    client.post("/chat", json={"user_id": "u1", "session_id": sid, "message": "second"})
    msgs = client.get(f"/sessions/{sid}/messages").json()
    assert [m["content"] for m in msgs][:3] == ["first", "api reply", "second"]


def test_chat_can_force_a_new_session_for_same_caller(client):
    first = client.post("/chat", json={"user_id": "u1", "message": "first"}).json()
    second = client.post("/chat", json={
        "user_id": "u1",
        "message": "new call",
        "new_session": True,
    }).json()
    assert second["session_id"] != first["session_id"]
    assert len(client.get("/sessions", params={"user_id": "u1"}).json()) == 2


def test_chat_rejects_cross_caller_session_reuse(client):
    alice = client.post("/chat", json={"user_id": "alice", "message": "private"}).json()
    bob = client.post("/chat", json={
        "user_id": "bob",
        "session_id": alice["session_id"],
        "message": "hello",
    }).json()
    assert bob["session_id"] != alice["session_id"]
    alice_messages = client.get(
        f"/sessions/{alice['session_id']}/messages"
    ).json()
    assert [message["content"] for message in alice_messages] == ["private", "api reply"]


def test_empty_message_rejected(client):
    assert client.post("/chat", json={"user_id": "u1", "message": "  "}).status_code == 400


def test_sessions_scoped_by_user(client):
    client.post("/chat", json={"user_id": "alice", "message": "hi"})
    client.post("/chat", json={"user_id": "bob", "message": "hi"})
    assert len(client.get("/sessions", params={"user_id": "alice"}).json()) == 1


def test_delete_session(client):
    sid = client.post("/chat", json={"user_id": "u1", "message": "hi"}).json()["session_id"]
    client.delete(f"/sessions/{sid}")
    assert client.get(f"/sessions/{sid}/messages").json() == []
