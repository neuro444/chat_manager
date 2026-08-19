"""Layer 18 — hangup delay hint.

The flag says the call is over; the delay says how long to wait so TTS can
finish speaking. No timer here — telephony owns the waiting.
"""
import json
import config
from providers.fake_provider import FakeProvider
from service import handle_message

END = json.dumps({
    "answer": "Done. CakeWorld Alpharetta.",
    "call_ended": True,
    "order_placed": True,
    "To_manager": False,
    "tools_called": True,
})


def test_default_delay_is_20_seconds():
    assert config.CALL_END_DELAY_SECONDS == 20


def test_ended_call_carries_the_delay(repo):
    out = handle_message(repo, FakeProvider(END), "+91", None, "that's all")
    assert out["call_ended"] is True
    assert out["end_delay_seconds"] == config.CALL_END_DELAY_SECONDS


def test_open_call_has_no_delay(repo):
    out = handle_message(repo, FakeProvider("Anything else?"), "+91", None, "hi")
    assert out["call_ended"] is False
    assert out["end_delay_seconds"] == 0


def test_api_returns_the_flag_and_delay(tmp_path):
    import api
    from fastapi.testclient import TestClient
    from storage.sqlite_store import SQLiteStore

    repo = SQLiteStore(str(tmp_path / "d.db")); repo.init_db()
    api._repo, api._provider = repo, FakeProvider(END)
    body = TestClient(api.app).post(
        "/chat", json={"user_id": "+91", "message": "done"}).json()
    assert body["call_ended"] is True
    assert body["end_delay_seconds"] == config.CALL_END_DELAY_SECONDS
    repo.close(); api._repo = api._provider = None
