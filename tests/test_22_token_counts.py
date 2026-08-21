"""Layer 22 — token accounting.

Two sources that must never be silently conflated: the API's reported usage
(what you are billed for) and the local tiktoken count (always available).
`token_source` says which one a caller is reading.
"""
import pytest
from fastapi.testclient import TestClient

import config
import tokens


@pytest.fixture
def client(tmp_path):
    import api
    from providers.fake_provider import FakeProvider
    from storage.sqlite_store import SQLiteStore

    repo = SQLiteStore(str(tmp_path / "tok.db"))
    repo.init_db()
    api._repo = repo
    api._provider = FakeProvider("a fake reply")
    yield TestClient(api.app)
    repo.close()
    api._repo = api._provider = None


# ── counting ──────────────────────────────────────────────────────────────

def test_counts_real_tokens_not_characters():
    """tiktoken must be doing the work, not len(text) // 4."""
    assert tokens.count_text("two samosas please") == 4


def test_empty_text_is_zero():
    assert tokens.count_text("") == 0
    assert tokens.count_text(None) == 0


def test_message_count_includes_per_message_overhead():
    """Chat serialization adds role/delimiter tokens per message."""
    msgs = [{"role": "user", "content": "hi"}]
    assert tokens.count_messages(msgs) > tokens.count_text("hi")


def test_message_count_grows_with_conversation():
    one = tokens.count_messages([{"role": "user", "content": "two samosas"}])
    two = tokens.count_messages([
        {"role": "user", "content": "two samosas"},
        {"role": "assistant", "content": "Sure, anything else?"},
    ])
    assert two > one


def test_tool_items_without_content_are_counted():
    """Responses API mixes function_call items into the same list."""
    msgs = [
        {"type": "function_call", "call_id": "c1", "name": "price_order",
         "arguments": '{"items":[{"name":"Samosa"}]}'},
        {"type": "function_call_output", "call_id": "c1",
         "output": '{"total":"25.83"}'},
    ]
    assert tokens.count_messages(msgs) > 10


def test_unknown_model_falls_back_to_configured_encoding(monkeypatch):
    """A new model name must not break counting."""
    monkeypatch.setattr(config, "LLM_MODEL", "some-unreleased-model-9")
    monkeypatch.setattr(tokens, "_encoder", None)
    monkeypatch.setattr(tokens, "_encoder_failed", False)
    assert tokens.count_text("two samosas please") == 4


# ── API usage extraction ──────────────────────────────────────────────────

class FakeUsage:
    def __init__(self, i, o, t=None):
        self.input_tokens = i
        self.output_tokens = o
        self.total_tokens = t if t is not None else i + o


class FakeResponse:
    def __init__(self, usage):
        self.usage = usage


def test_usage_extracted_from_response():
    got = tokens.usage_from_response(FakeResponse(FakeUsage(120, 45)))
    assert got == {"input_tokens": 120, "output_tokens": 45, "total_tokens": 165}


def test_missing_usage_returns_none():
    assert tokens.usage_from_response(FakeResponse(None)) is None
    assert tokens.usage_from_response(object()) is None


# ── report() ──────────────────────────────────────────────────────────────

class ProviderWithUsage:
    last_usage = {"input_tokens": 900, "output_tokens": 120, "total_tokens": 1020}


class ProviderWithoutUsage:
    last_usage = None


def test_report_prefers_the_api_numbers():
    """The API's count is what you are billed for; it wins."""
    r = tokens.report([{"role": "user", "content": "hi"}], "reply",
                      ProviderWithUsage(), "gpt-5.6-luna")
    assert r["input_tokens"] == 900
    assert r["output_tokens"] == 120
    assert r["token_source"] == "api"
    assert r["model_used"] == "gpt-5.6-luna"


def test_report_keeps_the_local_estimate_alongside():
    """A gap on tool turns is expected — both numbers stay visible."""
    r = tokens.report([{"role": "user", "content": "hi"}], "reply",
                      ProviderWithUsage(), "gpt-5.6-luna")
    assert "estimated_input_tokens" in r
    assert r["estimated_input_tokens"] != r["input_tokens"]


def test_report_falls_back_to_tiktoken():
    r = tokens.report([{"role": "user", "content": "two samosas"}], "Sure!",
                      ProviderWithoutUsage(), "gpt-5.6-luna")
    assert r["token_source"] == "tiktoken"
    assert r["input_tokens"] > 0 and r["output_tokens"] > 0
    assert r["total_tokens"] == r["input_tokens"] + r["output_tokens"]


def test_counting_never_raises_when_tiktoken_is_missing(monkeypatch):
    """Token accounting must never be the reason a call fails."""
    monkeypatch.setattr(tokens, "_encoder", None)
    monkeypatch.setattr(tokens, "_encoder_failed", True)
    assert tokens.count_text("two samosas please") > 0


# ── the /chat contract ────────────────────────────────────────────────────

TOKEN_FIELDS = ["model_used", "input_tokens", "output_tokens", "total_tokens"]


def test_chat_response_carries_the_token_fields(client):
    body = {"user_id": "+15551234567", "message": "two samosas"}
    data = client.post("/chat", json=body).json()
    for field in TOKEN_FIELDS:
        assert field in data, f"{field} missing from /chat response"
    assert data["model_used"] == config.LLM_MODEL
    assert isinstance(data["input_tokens"], int)
    assert data["input_tokens"] > 0
    assert data["output_tokens"] > 0


def test_input_tokens_reflect_the_assembled_prompt_not_just_the_message(client):
    """The count covers the full request — system prompt, menu, history."""
    data = client.post("/chat", json={"user_id": "+15551234567",
                                      "message": "hi"}).json()
    assert data["input_tokens"] > 500


def test_a_longer_conversation_reports_more_input_tokens(client):
    uid = "+15551234567"
    first = client.post("/chat", json={"user_id": uid, "message": "two samosas"}).json()
    second = client.post("/chat", json={"user_id": uid, "session_id": first["session_id"],
                                        "message": "and one gobi manchurian"}).json()
    assert second["input_tokens"] > first["input_tokens"]


def test_token_fields_cannot_be_overridden_by_the_model(client, monkeypatch):
    """A prompt echoing these names must not overwrite the measured values."""
    import service

    parsed = {"answer": "hi", "call_ended": False, "order_ready": False,
              "To_manager": False, "tools_called": False, "summary": "",
              "verbatim_user_chat": [], "input_tokens": 999999,
              "model_used": "evil-model"}
    assert "input_tokens" not in service._response_extensions(parsed)
    assert "model_used" not in service._response_extensions(parsed)


def test_usage_is_persisted_with_the_message(client):
    """Past turns stay auditable after the fact."""
    import api

    data = client.post("/chat", json={"user_id": "+15551234567",
                                      "message": "two samosas"}).json()
    msgs = api._repo.all_messages(data["session_id"])
    meta = [m for m in msgs if m.role == "assistant"][-1].metadata
    assert meta["token_usage"]["input_tokens"] == data["input_tokens"]


# ── latency and TTS characters ────────────────────────────────────────────

def test_latency_is_reported_per_turn(client):
    """Not a cost signal — it exists to flag unusually slow turns."""
    data = client.post("/chat", json={"user_id": "+15551234567",
                                      "message": "two samosas"}).json()
    assert "latency_ms" in data
    assert isinstance(data["latency_ms"], (int, float))
    assert data["latency_ms"] >= 0


def test_tts_chars_counts_only_the_spoken_answer(client):
    """The JSON envelope and flags are never sent to TTS — counting the raw
    model output would overstate the ElevenLabs bill substantially."""
    data = client.post("/chat", json={"user_id": "+15551234567",
                                      "message": "two samosas"}).json()
    assert data["tts_chars"] == len(data["answer"])


def test_per_turn_lists_accumulate_across_the_call(client):
    """latency_ms_per_turn is [t1, t2, t3] after three turns."""
    uid = "+15551234567"
    session_id = None
    for message in ["two samosas", "and a gobi manchurian", "that's all"]:
        body = {"user_id": uid, "message": message}
        if session_id:
            body["session_id"] = session_id
        data = client.post("/chat", json=body).json()
        session_id = data["session_id"]

    assert len(data["latency_ms_per_turn"]) == 3
    assert len(data["tts_chars_per_turn"]) == 3
    # The last entry is this turn.
    assert data["tts_chars_per_turn"][-1] == data["tts_chars"]
    assert data["latency_ms_per_turn"][-1] == data["latency_ms"]


def test_lists_cover_every_turn_not_a_window(client):
    """All turns in the session, unbounded — deliberately NOT capped by
    HISTORY_WINDOW, which limits the prompt context, not this telemetry."""
    uid = "+15551234567"
    session_id = None
    turns = config.HISTORY_WINDOW + 5   # comfortably past the context window
    for i in range(turns):
        body = {"user_id": uid, "message": f"item number {i}"}
        if session_id:
            body["session_id"] = session_id
        data = client.post("/chat", json=body).json()
        session_id = data["session_id"]

    assert len(data["latency_ms_per_turn"]) == turns
    assert len(data["tts_chars_per_turn"]) == turns
    assert data["total_chars_tts"] == sum(data["tts_chars_per_turn"])


def test_total_chars_tts_is_the_sum_of_the_call(client):
    uid = "+15551234567"
    session_id = None
    for message in ["two samosas", "and a gobi manchurian"]:
        body = {"user_id": uid, "message": message}
        if session_id:
            body["session_id"] = session_id
        data = client.post("/chat", json=body).json()
        session_id = data["session_id"]

    assert data["total_chars_tts"] == sum(data["tts_chars_per_turn"])
    assert data["total_chars_tts"] > data["tts_chars"]  # more than this turn


def test_first_turn_has_a_single_entry(client):
    data = client.post("/chat", json={"user_id": "+15551234567",
                                      "message": "hi"}).json()
    assert data["tts_chars_per_turn"] == [data["tts_chars"]]


def test_separate_calls_do_not_share_telemetry(client):
    """A new session starts its lists over — these are per-call, not per-caller."""
    uid = "+15551234567"
    first = client.post("/chat", json={"user_id": uid, "message": "two samosas"}).json()
    client.post("/chat", json={"user_id": uid, "session_id": first["session_id"],
                               "message": "and a chai"}).json()
    fresh = client.post("/chat", json={"user_id": uid, "message": "hello again",
                                       "new_session": True}).json()
    assert len(fresh["tts_chars_per_turn"]) == 1


def test_telemetry_survives_an_unreadable_history(monkeypatch):
    """Telemetry must never break a live call."""
    class BrokenRepo:
        def all_messages(self, session_id):
            raise RuntimeError("db gone")

    got = tokens.session_history(BrokenRepo(), "s1")
    assert got == {"latency_ms_per_turn": [], "tts_chars_per_turn": []}


def test_tts_chars_handles_an_empty_answer():
    assert tokens.count_tts_chars("") == 0
    assert tokens.count_tts_chars(None) == 0


def test_latency_fields_cannot_be_overridden_by_the_model():
    import service

    parsed = {"answer": "hi", "call_ended": False, "order_ready": False,
              "To_manager": False, "tools_called": False, "summary": "",
              "verbatim_user_chat": [], "latency_ms": 0.001,
              "total_chars_tts": 1, "latency_ms_per_turn": []}
    ext = service._response_extensions(parsed)
    for field in ("latency_ms", "total_chars_tts", "latency_ms_per_turn"):
        assert field not in ext
