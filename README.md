# Chat Manager

A channel-agnostic restaurant conversation API built with FastAPI. It provides
session history, cross-session memory, menu grounding, deterministic order
pricing, structured response flags, optional speech-to-text, and optional
ElevenLabs text-to-speech.

## Start with Docker

```bash
cp .env.example .env
# Add the required API credentials to .env.
docker compose up --build -d
curl http://127.0.0.1:8000/health
```

The API runs on port `8000` by default. SQLite data is persisted in the Docker
volume `chat_manager_data`.

## Primary endpoint

```http
POST /chat
Content-Type: application/json
```

```json
{
  "user_id": "customer-123",
  "session_id": null,
  "message": "I would like two samosas"
}
```

Reuse the returned `session_id` on subsequent turns. The response contains the
spoken/displayed `answer` and control fields including `call_ended`,
`order_ready`, structured `order`, `To_manager`, `Transfer_to_Manager`, and
`tools_called`.

See [integration.md](integration.md) for the complete API contract, audio flow,
endpoint reference, and client examples.

## Tests

```bash
pytest
```

The offline suite contains 152 tests and does not make paid model calls.

## Security

The API currently has no authentication. Keep it on a private network or behind
an authenticated reverse proxy before exposing it publicly.
