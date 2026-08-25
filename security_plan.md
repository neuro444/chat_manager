# Chat Manager — Security & Storage Plan

**Status:** draft for review · **Date:** 2026-08-19 · **Branch:** local, pre-VPS
**Scope:** `chat_manager_repo` only. Findings imported from the catering-brain
encryption review are marked **[from CB review]** where the same class of issue
applies here.

## What We're Building

A phone-ordering chat API (FastAPI + SQLite today) that runs locally on a Mac and
must ship to a Namecheap VPS via Docker Compose. Every conversation record is tied
to a **phone number used directly as the primary key** (`user_id` IS the caller's
E.164 number — see the docstring in `api.py`). That single design choice makes this
repo a PII store, so it inherits nearly every finding from the catering-brain
encryption review, plus a more urgent one of its own: **there is no authentication
at all.**

This plan fixes access control first, then storage, then encryption at rest. That
order is deliberate: field-level encryption on a wide-open API protects nothing.

---

## Integrated External Repository Plan — Outside This Repository

The following responsibilities belong to whichever external application
integrates with `chat_manager_repo`. They must not be implemented here unless
this repository's scope is deliberately expanded later:

- Phone-call setup, routing, status, termination, and provider lifecycle.
- Telephony, Plivo, WhatsApp, or other provider webhook authentication.
- Audio streaming, buffering, voice-activity detection, and channel codecs.
- Mapping an external call or channel ID to this API's `user_id` and `session_id`.
- Reusing the returned `session_id` for every turn in the same conversation.
- Sending transcripts into `/chat` and playing or displaying only `answer`.
- Acting on `call_ended`, `order_ready`, structured `order`, `To_manager`, and
  `tools_called`. The external system submits ready orders and records whether
  its order service accepted them.
- Creating manager notifications from `summary` and `verbatim_user_chat`.
- Server-to-server printing and revocable device-scoped print tokens.
- Typesense or any other search/analytics index not present in this repository.

The external repository must authenticate its own users, devices, and provider
webhooks. When calling this API, it must use the generic client credential that
`chat_manager_repo` will require; `/chat` must not depend on any particular
telephone or messaging provider.

The security boundary between repositories is the HTTP API contract. This
repository owns authentication and authorization of incoming API requests,
conversation/session storage, menu and LLM processing, optional `/stt` and
`/tts` helpers, and structured response fields. The external repository owns
transport-specific security and all downstream actions triggered by those
fields.

---

## Current vs Target

| Area | Current (verified today) | Target |
|---|---|---|
| Auth on staff endpoints | **None** — `/callers`, `/sessions`, `/search`, `DELETE` are fully open | API key (or basic auth) on all staff routes |
| Cross-caller isolation | `GET /sessions/{id}/messages` takes no `user_id` — any session id reads any caller's transcript | Session ownership checked per request |
| CORS | Not configured anywhere in the repo | Explicit allowlist, committed to git **[from CB review]** |
| HTTPS / headers | Nothing in repo; would live only on the server | nginx + certbot config checked into version control **[from CB review]** |
| Database | SQLite at `/data/chat_manager.db` in a named volume | SQLite fine for one replica; Mongo path already exists for scale-out |
| Encryption at rest | **None.** Phone numbers + transcripts in plain text **[from CB review]** | LUKS full-disk on the VPS as baseline |
| Phone numbers in analytics | N/A today (no telemetry yet) | Salted hash if telemetry is ever added **[from CB review guardrail]** |
| Transcript logging | `service.py` prints full LLM responses to stdout → docker logs | Redact or gate behind `DEBUG_CONTEXT` |
| Secrets | `.env` correctly gitignored; `.env.example` has empty values ✅ | Keep; add pre-commit grep |

---

## Verified Findings

These were confirmed against the **running container** on `127.0.0.1:8001`, not
read off the source. Evidence is included because "no auth" is easy to
under-rate until you see the response body.

### 1. CRITICAL — No authentication on any endpoint

```bash
$ curl -s http://127.0.0.1:8001/callers
[{"user_id":"docker-test-user","session_count":1,"message_count":2,...}]
```

`/callers` is the dashboard's left rail: it returns **the full list of every
caller's phone number** with activity counts. Unauthenticated. On a public VPS
this is a phone-number dump endpoint.

Currently mitigated *only* by the compose port binding `127.0.0.1:8001->8000`,
which is good hygiene and the reason this is not already a live breach. But that
binding is the *sole* control — the moment nginx proxies this service (which
`vps_instructions.md` implies is next), it is public. **The port binding is
load-bearing security right now and nothing in the repo says so.**

### 2. CRITICAL — IDOR on transcript reads

```bash
$ curl -s http://127.0.0.1:8001/sessions/1bd723ab-.../messages
[{"seq":1,"role":"user","content":"Hi",...},{"seq":2,"role":"assistant",...}]
```

`GET /sessions/{session_id}/messages` accepts **no `user_id`** and performs no
ownership check (`api.py`). Any session id → the full transcript. Session ids are
UUID4 so they are not guessable, but they are handed to clients, appear in logs,
and are printed to stdout by `service.py`. Same for `DELETE /sessions/{id}`,
which returned HTTP 200 to an unauthenticated caller.

Worth calling out: `storage/base.py` explicitly documents `user_id` on
`search_messages` as *"a security boundary, not a convenience — omitting it leaks
one user's history to another."* Both store implementations honour that contract
correctly. **The storage layer is the well-built part; the API layer above it
simply doesn't use the boundary.** That is the cheapest class of bug to fix.

### 3. HIGH — Transcripts written to container logs — ✅ FIXED 2026-08-19

`service.py:142` and `:176`:

```python
print(f"[llm_raw_response] session_id={session_id} response={raw!r}", flush=True)
print(f"[chat_result] {json.dumps(result, ensure_ascii=False)}", flush=True)
```

Full model responses and the complete result payload went to stdout
unconditionally — not behind the existing `DEBUG_CONTEXT` flag — so
`docker compose logs` held plain-text order conversations indefinitely.

**Fixed:** the three content-bearing calls now route through a `_debug()` helper
gated on `config.DEBUG_CONTEXT`. Timing lines (`[llm_call_start]`,
`[llm_call_complete]`) are deliberately left ungated — they carry no message
content and are useful ops signal in production. Verified silent with the flag
off, verbose with it on. Server `.env` must simply omit `DEBUG_CONTEXT`.

Note this could not be solved with `.gitignore`: `service.py` is application code
that must ship to the VPS. Gitignore controls repo contents, not server runtime.

### 4. MEDIUM — No CORS config in the repo **[from CB review]**

Verified: no `CORSMiddleware` anywhere. Unlike catering-brain, this repo is not
currently misconfigured — it's *unconfigured*, which is safer (browsers block
cross-origin by default) but means the dashboard's future origin will get fixed
under deadline pressure, and the `allow_origins=["*"] + allow_credentials=True`
mistake from catering-brain is exactly what gets reached for. Set the allowlist
now, in git, before it's urgent.

Per FastAPI docs: with `allow_credentials=True`, wildcards are *invalid* for
origins, methods, and headers — they must be enumerated.

### 5. MEDIUM — No HTTPS/nginx config in version control **[from CB review]**

Identical to the catering-brain finding. `vps_instructions.md` covers git and
compose but never nginx, TLS, or security headers, so that layer will be
hand-rolled on the box and unreviewed. Commit it.

### 6. MEDIUM — `.env` is not in `.dockerignore`'s effective protection path

`.env` *is* listed in `.dockerignore` ✅ and in `.gitignore` ✅ — good. But
`docker-compose.yml` uses `env_file: - .env`, so secrets reach the container at
runtime via environment, where `docker inspect` exposes them to any local user.
Acceptable for a single-tenant VPS; note it as accepted risk.

Also: `.gitignore` uses `*.md` + `!README.md` + `!integration.md`, which means
**this file is gitignored.** Decide deliberately — a security plan that isn't in
version control can't be reviewed. Recommend `!security_plan.md`.

### 7. MEDIUM — SQLite shared connection without WAL (upgraded from LOW)

`storage/sqlite_store.py:70` opens one connection with `check_same_thread=False`
and shares it across uvicorn's threadpool, in `journal_mode=delete` with
`synchronous=FULL`. Not a vulnerability, but benchmarking (above) shows reads
block writes — a staff dashboard load can stall a live call's message write.
`busy_timeout` is already 5000 ms, so it degrades into latency rather than
errors. Enable WAL.

---

## Storage: SQLite vs MongoDB

**Recommendation: stay on SQLite.** It is not close — measured at your stated
volume, SQLite has ~57,000x headroom. Move to Mongo only for a second replica.

### Measured capacity at 9,000 calls/month

Benchmarked on this machine against the real `SQLiteStore`, writing 9,000 calls
x 14 messages = **126,000 messages**:

| Metric | Result | Verdict |
|---|---|---|
| Full month of writes | 145 s of total DB time | trivial |
| Sustained write rate | 866 msg/s (concurrent-ish), 2,763 msg/s single-stream | — |
| **Your actual average load** | **0.049 writes/sec** | **~57,000x headroom** |
| DB size after 1 month | 61 MB | ~740 MB/year |
| `list_callers` (dashboard) at full size | 47 ms | fine |
| FTS transcript search at full size | 272 ms | acceptable, watch it |

9,000 calls/month is ~12.5 calls/hour. Even at a 100x burst (peak dinner rush,
every line ringing) you are at ~5 writes/sec against a floor of 2,700. **SQLite
is not your bottleneck — the LLM call is.** Each turn waits on an OpenAI round
trip measured in hundreds of ms; the DB write is 0.36 ms of that.

Two things to fix rather than replacing the engine:

- **Turn on WAL.** Measured: `journal_mode=WAL` + `synchronous=NORMAL` gives
  **3.8x** on writes (2,763 -> 10,467 msg/s) and, more importantly, lets reads
  proceed during writes. Today the DB is `journal_mode=delete`,
  `synchronous=FULL`, and `append_message()` fsync-commits on every single
  message — so a staff member loading the dashboard can block a live call's
  write. That is the real concurrency risk at your volume, not throughput.
- **Watch FTS growth.** 272 ms at one month, and the `messages_fts` index grows
  unbounded. Revisit at ~12 months (~740 MB) or add a retention policy — which
  you likely want for privacy reasons anyway (see below).

**Retention is the better lever than encryption.** 740 MB/year of plain-text
phone numbers and transcripts is a growing liability. Deleting call transcripts
after N months shrinks both the breach blast radius and the FTS index at once.

The Mongo path is genuinely ready — `storage/mongo_store.py` implements the full
`ChatRepository` protocol, `pymongo==4.17.0` is pinned, `init_db()` creates the
text index, and `STORAGE=mongo` switches it via the factory in
`storage/__init__.py`. Both stores scope `search_messages` by `user_id` correctly.
So this is a config flip, not a migration project — **but it buys you nothing
security-wise today, and costs you two new problems:**

1. `MONGO_URI=mongodb://localhost:27017` has **no credentials and no TLS.** An
   auth-less mongod is a well-known mass-scanning target. You would be trading a
   file-permissions problem for a network-service problem.
2. **MongoDB Community Edition has no built-in encryption at rest.** Native
   `enableEncryption`/`encryptionKeyFile` (encrypted WiredTiger) is an
   **Enterprise** feature. So switching to Mongo does *not* solve at-rest
   encryption — you would still land on full-disk encryption, the same answer as
   SQLite. This directly answers the open question from the CB review: there is no
   "enable encryption" flag on either engine at the tier you're running.

There is also no `mongo` service in `docker-compose.yml`, so adopting it means
standing up and hardening a database container too.

**If/when you do switch:** require SCRAM auth in the URI, bind mongod to the
compose network only (never a host port), enable TLS (`?tls=true`), create a
least-privilege `readWrite` user scoped to the `chat_manager` DB, and put the
password in a secret rather than `MONGO_URI`.

---

## Encryption at Rest **[from CB review]**

Same conclusion as catering-brain, same reasoning, now confirmed for both engines:

- **Confirm Namecheap's default first.** Most VPS disks are unencrypted by
  default; verify before assuming either way.
- **Full-disk (LUKS) is the right near-term baseline.** Transparent to the app,
  breaks no search behaviour, protects the SQLite file, the Mongo data dir, *and*
  the docker logs from finding #3. Only protects data when the disk is offline.
- **LUKS is a planned migration with downtime, not a config flag** — on most VPS
  providers it means a rebuild/restore, since you cannot encrypt a mounted root
  in place. Schedule it.
- **Field-level encryption conflicts with search here, exactly as in
  catering-brain.** `sqlite_store.py` uses an FTS5 index over `content`, and the
  Mongo store uses a `TEXT` index. Encrypting `content` breaks both.

**Open question for the feature owner** (mirrors the CB question, and the answer
should probably match): *Is free-text search over transcripts a hard requirement
for the staff dashboard, or can caller lookup move to a deterministic/hashed
index so transcript columns can be field-encrypted?*

Note that `user_id` (the phone number) is a **primary key and foreign key** across
`users`, `sessions`, and `messages`. Field-encrypting or hashing it is therefore a
schema migration, not a column change — decide before the data set grows.

**Phone privacy guardrail [from CB review]:** no telemetry or cost-analytics
exists in this repo today, so nothing needs hashing yet. If cost/analytics is ever
correlated back to a caller, use a salted hash rather than the raw number.

---

## Phases

Golden Rule callout below applies to every phase.

### Phase 1 — Access control (do before any public exposure)
*Blast radius: local only. No VPS impact.*
1. Add an API-key dependency (`APIKeyHeader`) on `/callers`, `/sessions`,
   `/search`, `/stt`, `/tts`, and `DELETE /sessions/{id}`. Leave `/health` open.
   `/chat` needs its own story — it's called by the voice channel, so it needs a
   shared secret from the telephony webhook, not a staff key.
2. Require `user_id` on `GET /sessions/{id}/messages` and `DELETE`, and verify
   session ownership via `get_session()` before returning anything. Return 404,
   not 403, on mismatch.
3. Add explicit `CORSMiddleware` with the dashboard origin enumerated. Never
   `["*"]` with credentials.
4. Tests: assert 401 unauthenticated, and that caller A cannot read caller B's
   session. **Risk if skipped:** the two CRITICALs ship.

### Phase 2 — Log hygiene
*Blast radius: local only.*
5. ✅ Done — `[llm_raw_response]` / `[chat_result]` gated behind `DEBUG_CONTEXT`.
6. Enable WAL + `synchronous=NORMAL` in `SQLiteStore.__init__` (measured 3.8x,
   and removes read/write blocking). Low risk, high value.

### Phase 3 — Transport & server config in git
*Blast radius: none until deployed.*
7. Commit `deploy/nginx.conf` (TLS, HSTS, security headers, proxy to
   `127.0.0.1:8001`) and document certbot. Keep the compose port bound to
   localhost so nginx stays the only public entry.
8. Add `!security_plan.md` to `.gitignore` so this file is reviewable.

### Phase 4 — Encryption at rest
*Blast radius: **downtime**. Requires a maintenance window.*
9. Confirm Namecheap disk-encryption default.
10. Plan the LUKS migration; back up `chat_manager_data` first
   (`vps_instructions.md` already warns against `down -v`).

### Phase 5 — Deferred, decision-gated
11. Field-level encryption — blocked on the search question above.
12. Mongo switch — only for multi-replica, and only with auth + TLS.

---

> ## 🔒 Migration Golden Rule
> **Never touch the live system until the replacement is verified.** Phases 1–3
> are code changes testable entirely on the Mac against the existing container.
> Phase 4 (LUKS) and any Mongo switch touch persistent data — build in parallel,
> verify at the raw IP/port, restore from a tested backup, and make the traffic
> cutover the last step. Do not run `docker compose down -v` on the VPS.

---

## Accepted Risks

- Secrets visible via `docker inspect` to local users (single-tenant VPS).
- Full-disk encryption does not protect a *running* system — only a stolen or
  offline disk. Field-level encryption is the only fix, and it is search-blocked.
- Session UUIDs remain bearer-ish identifiers until Phase 1 lands.
