# Chat Manager API Integration Guide

This document describes the API that exists in this repository. The API is
channel-agnostic: clients may send text directly or optionally use the included
speech endpoints.

## Base URL

Local Docker default:

```text
http://127.0.0.1:8000
```

Production clients should use an authenticated HTTPS reverse proxy. The API
itself currently performs no authentication.

## Conversation lifecycle

1. Choose a stable `user_id` for the customer.
2. Send the first message to `POST /chat` with `session_id: null`.
3. Save the returned `session_id`.
4. Send that `session_id` with every later message in the conversation.
5. Display or speak only the returned `answer`.
6. Act on the remaining JSON control fields.
7. Stop sending turns when `call_ended` is `true`.

The same flow works for browsers, mobile apps, kiosks, backend services, and
voice integrations.

## Layered context transport

1. The client sends only `user_id`, `session_id`, and the current `message`.
2. Use one stable `user_id` per customer; a normalized phone number is optional.
3. The server stores and retrieves the customer's name using `user_id`.
4. The server also retrieves relevant preferences and previous sessions by `user_id`.
5. The returned `session_id` must be reused for later turns in that conversation.
6. Current history and its rolling summary are loaded internally by `session_id`.
7. The server adds the system prompt, menu, profile, memory, and current message.
8. Clients must not resend names, history, summaries, menu data, or memory layers.
9. The response returns `answer`, the session ID, and machine-readable control fields.
10. For audio, transcribe first, send the text to `/chat`, then send only `answer` to `/tts`.

## Health check

```http
GET /health
```

Example response:

```json
{
  "status": "ok",
  "storage": "sqlite",
  "model": "gpt-5.6-luna"
}
```

## Process a chat turn

```http
POST /chat
Content-Type: application/json
```

Request:

```json
{
  "user_id": "customer-123",
  "session_id": null,
  "message": "I would like two samosas"
}
```

### Request fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `user_id` | string | No | Stable customer identity; defaults to `default` |
| `session_id` | string or null | No | `null` initially; reuse the returned ID afterward |
| `message` | string | Yes | Current finalized user utterance or text message |

Blank messages return HTTP `400`.

### Response

```json
{
  "answer": "Certainly, two samosas. Is that everything for your order?",
  "session_id": "81068fc8-5d86-4f67-87fe-a75034a2f42d",
  "call_ended": false,
  "order_ready": false,
  "To_manager": false,
  "tools_called": false,
  "order": null,
  "summary": "",
  "verbatim_user_chat": [],
  "end_delay_seconds": 0
}
```

### Response fields

| Field | Type | Meaning |
|---|---|---|
| `answer` | string | The only value intended for the customer |
| `session_id` | string | Send with the next turn |
| `call_ended` | boolean | Conversation is complete |
| `order_ready` | boolean | A verified pickup order is ready for external submission |
| `order` | object or null | Structured order from the actual pricing-tool result |
| `To_manager` | boolean | Cake or catering request requires manager follow-up |
| `tools_called` | boolean | A server-side LLM tool actually ran for this response |
| `summary` | string | Manager-handoff summary; otherwise empty |
| `verbatim_user_chat` | string array | Original user messages for manager handoff |
| `end_delay_seconds` | integer | Optional delay before closing an audio channel |

`tools_called` is verified against actual provider tool execution. It is not
accepted solely because the model wrote `true`.

`order_ready` does not mean that an order was placed. Chat Manager constructs
`order` from the successful `price_order` tool result and returns it to the
caller. The integrating service should submit that object to its order system
and separately record the order system's acceptance or rejection. Never parse
items, quantities, or totals from `answer`.

### Completed pickup order

```json
{
  "answer": "Your order is confirmed and will be ready in approximately twenty to thirty minutes. Thanks for calling CakeWorld Alpharetta.",
  "session_id": "81068fc8-5d86-4f67-87fe-a75034a2f42d",
  "call_ended": true,
  "order_ready": true,
  "To_manager": false,
  "tools_called": true,
  "order": {
    "customer_name": "Priya",
    "fulfillment": "pickup",
    "items": [{"name":"Veg Biriyani","quantity":3,"unit_price":"13.99","line_total":"41.97"}],
    "subtotal": "41.97",
    "tax": "3.25",
    "total": "45.22",
    "preparation_minutes": "20-30"
  },
  "summary": "",
  "verbatim_user_chat": [],
  "end_delay_seconds": 20
}
```

### Manager handoff

```json
{
  "answer": "I’ll send your catering requirements to our manager, who will contact you.",
  "session_id": "81068fc8-5d86-4f67-87fe-a75034a2f42d",
  "call_ended": true,
  "order_ready": false,
  "To_manager": true,
  "tools_called": false,
  "order": null,
  "summary": "Customer requests office catering for approximately sixty people next Friday.",
  "verbatim_user_chat": [
    "I need catering for an office event.",
    "It’s a company lunch for about sixty employees next Friday."
  ],
  "end_delay_seconds": 20
}
```

The integrating application decides how to notify a manager. This repository
only returns and persists the handoff data.

## Optional speech-to-text

```http
POST /stt
Content-Type: multipart/form-data
```

Upload one form field named `file`:

```bash
curl -X POST http://127.0.0.1:8000/stt \
  -F 'file=@utterance.webm'
```

Response:

```json
{"text":"I would like two samosas"}
```

`/stt` only transcribes. It does not create a user, session, or chat turn. Send
the returned `text` to `/chat` as `message`.

## Optional text-to-speech

```http
POST /tts
Content-Type: application/json
```

Request:

```json
{"text":"Certainly, two samosas. Is that everything for your order?"}
```

Response:

```text
Content-Type: audio/mpeg
Body: MP3 bytes
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/tts \
  -H 'Content-Type: application/json' \
  -d '{"text":"Certainly, two samosas. Is that everything for your order?"}' \
  --output reply.mp3
```

Send only `/chat`'s `answer` field to `/tts`. Never speak `summary`,
`verbatim_user_chat`, or control fields. `/tts` returns HTTP `503` when
ElevenLabs credentials are not configured.

## Complete optional audio flow

```text
client audio
   → POST /stt
   ← {"text":"..."}
   → POST /chat with text + user_id + session_id
   ← structured conversation JSON
   → POST /tts with JSON.answer
   ← MP3 audio
```

Audio is optional. Text clients call `/chat` directly.

## Conversation and history endpoints

### List users

```http
GET /callers
```

Returns user identifiers with session count, message count, name, and last
activity.

### List a user's sessions

```http
GET /sessions?user_id=customer-123
```

Returns session IDs, titles, message counts, timestamps, and rolling summaries.

### Read a session transcript

```http
GET /sessions/{session_id}/messages
```

Returns messages ordered by sequence:

```json
[
  {
    "seq": 1,
    "role": "user",
    "content": "Hi",
    "created_at": "2026-08-19T15:16:00+00:00"
  }
]
```

### Search a user's past messages

```http
GET /search?user_id=customer-123&q=samosa
```

### Delete a session

```http
DELETE /sessions/{session_id}
```

Deletion removes the session and its messages and cannot be undone through the
API.

## JavaScript example

```javascript
let sessionId = null;

async function sendTurn(userId, message) {
  const response = await fetch("https://api.example.com/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      session_id: sessionId,
      message
    })
  });

  if (!response.ok) throw new Error(await response.text());

  const result = await response.json();
  sessionId = result.session_id;

  displayOrSpeak(result.answer);

  if (result.To_manager) createManagerHandoff(result);
  if (result.order_ready) submitOrder(result.order);
  if (result.call_ended) finishConversation(result.end_delay_seconds);

  return result;
}
```

## Python example

```python
import requests

session_id = None

def send_turn(user_id: str, message: str) -> dict:
    global session_id
    response = requests.post(
        "https://api.example.com/chat",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
        },
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()
    session_id = result["session_id"]
    return result
```

## Persistence and concurrency

SQLite is the default and Docker stores it in the persistent
`chat_manager_data` volume. Use one API worker with SQLite. Configure
`STORAGE=mongo` before running multiple replicas or workers.

Every assistant response persists its control fields, model, and LLM latency in
message metadata.

## Security requirements

The current endpoints do not authenticate callers or authorize access to
`user_id` and `session_id`. Before exposing the API publicly:

- Require authentication at a reverse proxy or application gateway.
- Use HTTPS.
- Restrict staff/history endpoints separately where possible.
- Rate-limit `/chat`, `/stt`, and `/tts`.
- Validate that clients may access the supplied user and session IDs.
- Set upload-size limits for `/stt` at the reverse proxy.

## Interactive documentation

When FastAPI documentation is enabled, the schemas can also be inspected at:

```text
/docs
/openapi.json
```
