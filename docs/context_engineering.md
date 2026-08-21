# Context Engineering

This document describes how Chat Manager assembles model context, preserves an
active phone-order conversation, recalls prior calls for the same phone number,
and keeps staff search separate from model memory.

## Identity and conversation boundaries

- `user_id` is the caller's normalized phone number.
- A session represents one call/order conversation.
- Current-session history is kept separate from cross-session context.
- Cross-session context is strictly scoped to the same phone number. Content
  from one phone number must never enter another caller's model context.
- A phone number is not treated as a person's identity. Multiple family members
  may share one phone and use different pickup names on different orders.
- Pickup names are interpreted within their dated call context. A name from one
  order must not be permanently assumed to identify every caller using that
  phone.

## Context budget

The application context budget is configured independently from the model's
maximum supported context window:

```env
MAX_CONTEXT_TOKENS=32000
RESERVED_FOR_REPLY=1500
HISTORY_WINDOW=20
CROSS_SESSION_SESSION_WINDOW=5
CROSS_SESSION_MESSAGE_WINDOW=40
```

`MAX_CONTEXT_TOKENS` was increased from 8,000 to 32,000 after a longer system
prompt exhausted the optional-context allocation. The 1,500-token reply reserve
is subtracted before input blocks are allocated.

The assembler currently uses `characters / 4` as its conservative trimming
estimate. Runtime token reporting is separate: `tokens.py` uses `tiktoken` and,
when available, prefers the provider's exact API usage because tool-calling
turns may involve multiple billed requests.

The configured layer weights are:

| Layer | Weight |
|---|---:|
| Menu/reference domain | 35% |
| Current-session history | 30% |
| Current-session summary | 15% |
| Prior-call memory | 15% |
| Caller profile | 5% |

Reference data is capped at its allocated share. It cannot borrow the space
reserved for conversation history or other context layers.

## The lost-history incident

The former 8,000-token configuration packed context in this effective order:

1. System prompt
2. Menu/reference data
3. Conversation history, if any space remained

After the ordering prompt grew, the allocation looked approximately like this:

```text
Application context budget        8,000
Reserved for response            -1,500
System prompt                    ~-5,392
Available after prompt           ~1,108
Menu requirement                 ~-1,435
Available for active history          0
```

The database still contained every turn and the client continued sending the
same session ID. However, the model received only the system prompt, a truncated
menu, and the latest message. A reply such as `yes` arrived without the preceding
item clarification, causing the assistant to restart with its greeting.

Evidence from production showed the same session ID on every request while the
input-token count remained nearly constant as the visible conversation grew.
Local context tests also proved that stored history and caller information were
absent from the assembled model request.

The safeguards are now:

- A 32,000-token application context budget.
- A hard cap on the menu/reference layer.
- Regression coverage for current-session history, caller scoping, summaries,
  prior calls, menu integrity, and budget weights.
- Full test-suite verification before deployment.

## Current-session history

The active session supplies recent caller and assistant turns through
`context/history.py`. The newest caller message is stored before the LLM call but
is excluded from the history block because the assembler appends it exactly once
as the final user message.

Current history is the authority for an in-progress order. Past-order items must
never be silently copied into the active order.

## Prior-call context

`context/memory.py` always supplies recent calls for the same phone number. It no
longer depends on keyword overlap or phrases such as “last time.” Keyword
matching remains useful for explicit staff search, but it is not the gate for
model memory.

The memory layer selects up to five recent sessions and distributes a maximum of
40 transcript messages fairly between them. With five available calls, each call
normally receives up to eight recent messages. One long call therefore cannot
hide the other four sessions.

Each prior call is rendered with:

- Call date and time in UTC.
- Completed or open status.
- Order type.
- Pickup/order name when present.
- Structured ordered items.
- Order total.
- Final call summary.
- Rolling conversation summary when present.
- Both caller and assistant transcript messages.

Example:

```text
Previous call — 2026-08-20 12:55 UTC — completed
- order type: pickup
- order name: Sri Krishna
- ordered items: 1 × Chilli Paneer
- order total: 12.92
- call summary: Pickup order for Sri Krishna: one Chilli Paneer, total 12.92.
- transcript:
  - assistant: What name should I place the order under?
  - caller: Sri Krishna
  - assistant: That's one Chilli Paneer at eleven ninety-nine...
```

Including both sides of the exchange is important: the bare reply `Sri Krishna`
only has reliable meaning beside the assistant's preceding name question.

## Pickup-name behavior

The system prompt tells the model to apply this priority:

1. Inspect current history and supplied dated prior calls.
2. Use the most recent applicable answer to “What name should I place the order
   under?”
3. Do not ask again when a usable name is already present.
4. If no applicable name exists, ask once.
5. If the caller explicitly declines or completes the flow without supplying a
   name, use `no_name_given`.

Completed pickup JSON includes both:

```json
{
  "name": "Sri Krishna",
  "order": {
    "customer_name": "Sri Krishna",
    "fulfillment": "pickup"
  }
}
```

The fallback is:

```json
{
  "name": "no_name_given",
  "order": {
    "customer_name": "no_name_given"
  }
}
```

`no_name_given` is an integration value, not customer-facing language. Summaries
should say `Unnamed pickup order`, never `Pickup order for no_name_given`.

If the caller responds to the name question by adding, removing, or changing an
item, that response is neither a name nor a refusal. The assistant must:

1. Keep `call_ended=false` and `order_ready=false`.
2. Modify the order.
3. Review the complete updated order.
4. Ask whether anything else is needed.
5. Avoid asking for the name a second time.
6. Use a volunteered name or, when the caller finishes without one,
   `no_name_given`.

## Required pickup flow

The prompt enforces this conversational order:

1. Resolve menu item and quantity questions.
2. Settle pickup versus delivery as a separate question.
3. Review the complete pickup order.
4. Ask once: “Would you like anything else?” This happens even when the caller
   previously said “that's all.”
5. Ask once for the pickup name when no applicable name is available.
6. Call `price_order` only after the review is accepted.
7. Return the priced order, preparation time, completion flags, order type,
   name, and concise summary.

## Order classification and final JSON

Every completed interaction uses one normalized `order_type`:

- `pickup`
- `cake`
- `catering`
- `cake/catering`
- `delivery`

The value is normalized in `context/callflow.py`, returned through the API, and
persisted with the assistant message. Downstream Telephony emission includes the
type, answer, summary, caller transcript when applicable, and structured order.
Completed delivery redirects are emitted instead of being silently discarded.

## Cake and catering context

Cake and catering are callback-message workflows, not phone orders. The prompt
states that Divya does not take those orders, does not invent menus, flavors,
prices, options, or availability, and asks once for callback details. Regular
food pickup remains a separate flow.

Cake or catering data should ultimately be filtered from reference context when
it is not needed; telling the model to ignore supplied data is weaker than not
supplying that data.

## Search versus model memory

Model memory and staff search are intentionally different:

- Model memory always receives the five recent sessions for the same phone
  number. It is not keyword-gated.
- Selected-caller search searches sessions belonging to one phone number.
- Staff-wide search uses `/staff/search` to search across callers and sessions.

The staff-wide endpoint is protected by the API-key dependency. Results include
the phone number, session ID, matching preview, and timestamp. The dashboard has
a separate “Search all conversations…” input that opens the matched caller and
session. This capability must remain staff-only because it crosses caller
boundaries.

## Security invariants

- Cross-session model context is always restricted to the same `user_id`/phone.
- Staff-wide search is never used as automatic LLM context.
- Another caller's messages must never enter a phone-scoped request.
- Transcript-bearing debug logs remain gated behind `DEBUG_CONTEXT`.
- Model-generated token fields cannot overwrite measured token usage.

## Validation

The implementation is covered by tests for:

- Current-session history preservation.
- Five-session representation and the 40-message cap.
- Dated caller and assistant transcripts.
- Cross-phone isolation.
- Staff-wide search and API-key enforcement.
- Context-budget layer caps.
- Pickup flow, order flags, and JSON normalization.
- Token measurement and persisted usage metadata.

At the time this document was written, the complete suite passed with 205 tests.

## Server configuration

Required production values:

```env
MAX_CONTEXT_TOKENS=32000
RESERVED_FOR_REPLY=1500
CROSS_SESSION_SESSION_WINDOW=5
CROSS_SESSION_MESSAGE_WINDOW=40
```

After changing environment values or pulling context code, rebuild the API
container so both code and `.env` reach the running process:

```bash
cd /opt/chat_manager
git pull --ff-only origin main
docker compose up -d --build --force-recreate api
docker compose exec api python -c \
'import config; print(config.MAX_CONTEXT_TOKENS, config.CROSS_SESSION_SESSION_WINDOW, config.CROSS_SESSION_MESSAGE_WINDOW)'
curl -s http://127.0.0.1:8004/health
```
