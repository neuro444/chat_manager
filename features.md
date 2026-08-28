# Chat Manager, Telephony, Dashboard, and Printer Features

## Chat Manager

- LLM-based restaurant ordering and conversation management.
- Regular pickup food ordering with menu validation and `price_order` tool
  pricing.
- Order review, an "anything else?" confirmation, fulfillment selection, and
  customer-name collection.
- Structured JSON containing model-resolved `user_name`, order/callback `name`,
  `order_ready`, `order_type`, item prices, tax, total, preparation time,
  summaries, and call-control flags.
- Verified order construction uses the pricing tool—not raw LLM output—as the
  source of truth for items and money.
- Separate conversational cake/catering intake and manager-callback handoff.
- Delivery requests are redirected to the website without creating pickup
  orders.
- Live manager transfers remain separate from asynchronous manager callbacks.
- Business-hours handling for 11:00 AM to 11:00 PM every day.
- Prompt-based caller-name resolution from the current chat, session summary,
  and dated same-number history. Python does not extract, freeze, select, or
  inject a profile name into the conversation.
- Cross-session context includes up to five recent sessions with dates,
  transcripts, order details, names, and summaries.
- Caller-specific past-order questions are supported.
- SQLite, MongoDB, and in-memory storage implementations.
- API-key protection for data and chat endpoints.
- STT and TTS endpoints for browser testing.
- Per-turn input/output token counts, model name, latency, TTS characters, and
  cumulative call telemetry.

## Chat Manager Dashboard

- Caller list and caller search.
- Search across all callers and conversations.
- Search within one caller's calls.
- Session list and complete transcripts.
- Create a new caller or new call session.
- Type or speak as the caller for testing.
- Browser microphone transcription and assistant-response playback.
- Small standard copy and trash icons.
- Copy individual messages and the active session ID.
- Delete individual sessions or a caller and all associated sessions.
- Persistent expandable LLM-debug context for current and reopened sessions.
- The debug display includes:
  - Latest caller query
  - Current chat history
  - Session summary
  - Caller profile
  - Cross-session memory
  - Menu/reference data
  - System prompt
  - Complete combined LLM input
  - Pretty-printed raw LLM JSON output

## Telephony Gateway

- Plivo phone-call gateway connected to Chat Manager.
- Official Plivo V3 webhook-signature validation.
- Caller phone number is used as the Chat Manager user ID.
- Per-call session binding and state management.
- ElevenLabs voice generation and temporary MP3 caching.
- Plivo native `<Speak>` fallback if ElevenLabs fails.
- Brain-failure fallback to manager transfer.
- Speech recognition with language, menu hints, and the phone-call speech model.
- No-input reprompt loop so speech timeouts do not disconnect active calls.
- Live manager transfer with busy/no-answer handling.
- Explicit call ending after the final spoken confirmation.
- Hangup callback handling with duration and hangup-cause capture.
- Persistent audio, order, and cost Docker volumes.
- Typed outcome separation for completed pickup orders, cake/catering manager
  handoffs, and delivery redirects.
- Idempotency guards prevent duplicate order, handoff, and printer emissions.
- Operational APIs:
  - `GET /health`
  - `GET /orders/recent`
  - `GET /handoffs/recent`
  - `GET /cost/calls`

## Printer Integration

- Automatic printing when a finalized event is emitted.
- Pickup orders produce priced kitchen tickets.
- Cake, catering, and combined requests produce quote-free manager callback
  sheets.
- Callback sheets include caller number, resolved name, summary, and verbatim
  requirements.
- Delivery redirects are never printed as manager sheets.
- Production requests use
  `https://cakeworld.neuroheart.ai/print/order`.
- Production flow:

  ```text
  Telephony
  -> /print/order
  -> printer service on 127.0.0.1:7860
  -> persistent remote queue
  -> restaurant printer bridge
  -> physical printer and arrival sound
  ```

- Printer failures are logged but never interrupt or disconnect a phone call.
- Duplicate Plivo callbacks do not create duplicate print jobs.
- Bridge heartbeat and queue polling show whether the restaurant-side bridge is
  connected.

## Printer and Operations Consoles

The staff dashboard now lives in the separate `voice_central` repository. Its
Kitchen Orders tab consumes live pickup-order data from Telephony. Available
operational interfaces are:

- Automatic printer-client logs in the Telephony container.
- The existing production remote queue and restaurant printer bridge.
- `/orders/recent` for pickup-order records.
- `/handoffs/recent` for cake/catering and delivery records.
- `/cost/calls` for call duration and hangup information.
- The Chat Manager dashboard for caller sessions, transcripts, and LLM
  debugging.
- The live `voice_central` Kitchen Orders view for structured Telephony orders,
  polling, arrival alerts, filtering, and manual ticket printing.

The old `namaste-dashboard` UI was migrated into `voice_central`. Order-status
transitions are still not backed by a Telephony status-update endpoint, so new
phone orders currently enter the dashboard as `received`.

## New Multi-Repository Voice Central Integration

- Voice Central uses authenticated server-side BFF routes under
  `/dashboard-api/chat-manager/*` and `/dashboard-api/telephony/*`; upstream API
  keys are not exposed to browser JavaScript.
- Calls & Messages reads Chat Manager callers, sessions, and full transcripts.
- The Orders tab and main Dashboard merge completed Chat Manager orders with
  Telephony phone-order events, deduplicate by `session_id`, and prefer the
  Telephony record for phone orders.
- Completed browser/direct-chat orders still appear when no Telephony event was
  emitted for that session.
- The CRM view derives customer totals and order history from completed Chat
  Manager sessions.
- The Menu view reads the live pickup menu from Chat Manager and is read-only;
  cake and catering menus remain intentionally unavailable.
- Conversation names shown to staff come from structured session/order output.
  This display behavior is separate from the assistant's prompt-based name use.
- Protected BFF routes exist for LLM debug, manager handoffs, and call costs;
  their dedicated Voice Central UI components remain pending.
- WhatsApp history remains pending because the new repositories do not yet have
  a WhatsApp ingestion and persistence layer.
