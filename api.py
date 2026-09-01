"""HTTP API + staff dashboard.

Identity model: there is no login. `user_id` IS the caller's phone number,
supplied by the voice channel (browser mic today, telephony webhook later).
Staff read the dashboard; callers never see a screen.
"""
import hmac
import logging
import re
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import config
from providers import make_provider
from service import handle_message
from storage import make_repo
from menu.loader import menu_items

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chat_manager.api")


def check_api_key_configuration() -> bool:
    """Check whether both named API keys are configured and log appropriate status.

    Returns True only if TELEPHONY_API_KEY and DASHBOARD_API_KEY are both set.
    Each is checked (and warned about) independently, since either being unset
    disables auth on a different, real set of routes -- not an all-or-nothing
    single flag anymore.
    """
    telephony_set = bool(config.TELEPHONY_API_KEY)
    dashboard_set = bool(config.DASHBOARD_API_KEY)

    if not telephony_set:
        logger.warning(
            "SECURITY WARNING: TELEPHONY_API_KEY is not set — /chat accepts "
            "requests with no telephony key. Set TELEPHONY_API_KEY in your "
            "production environment (.env)."
        )
    if not dashboard_set:
        logger.warning(
            "SECURITY WARNING: DASHBOARD_API_KEY is not set — transcript, "
            "session, and order endpoints are publicly accessible without "
            "authentication. Set DASHBOARD_API_KEY in your production "
            "environment (.env)."
        )
    if telephony_set and dashboard_set:
        logger.info("API key authentication is ENABLED (X-API-Key required for guarded endpoints)")
        return True
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_api_key_configuration()
    yield


app = FastAPI(title="Chat Manager — Phone Ordering", lifespan=lifespan)

# Allows the voice_central dashboard (browser JS on a different origin)
# to call this API directly. telephony calls chat_manager server-to-server
# (no browser involved, CORS never applies there) and chat_manager's own
# bundled dashboard is served same-origin -- this is specifically for
# voice_central. Update allow_origins with the real production dashboard
# origin once that's known; localhost:3000 covers local dev for now.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
WEB = Path(__file__).parent / "web"


def require_dashboard_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    """Guard every route that exposes caller data other than /chat itself.

    Only the dashboard key is accepted here -- telephony has no legitimate
    reason to read or delete transcripts, so it is deliberately not one of
    the accepted keys on this dependency (see require_chat_key for /chat,
    which both callers may use).

    A no-op when config.DASHBOARD_API_KEY is unset, so local dev and the test
    suite run unchanged. /health stays open so Docker's healthcheck and the
    gateway's readiness probe work without any key.
    """
    if not config.DASHBOARD_API_KEY:
        return
    if not hmac.compare_digest(x_api_key, config.DASHBOARD_API_KEY):
        raise HTTPException(401, "invalid or missing API key")


def require_chat_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    """Guard /chat specifically -- the one route both callers legitimately use.

    The telephony gateway calls it for every live turn; the dashboard's own
    bundled UI calls it for staff live-testing. Either named key is accepted.
    A no-op when both keys are unset, matching require_dashboard_key's local-
    dev behavior.
    """
    if not config.TELEPHONY_API_KEY and not config.DASHBOARD_API_KEY:
        return
    if x_api_key and (
        hmac.compare_digest(x_api_key, config.TELEPHONY_API_KEY or "\0")
        or hmac.compare_digest(x_api_key, config.DASHBOARD_API_KEY or "\0")
    ):
        return
    raise HTTPException(401, "invalid or missing API key")

_repo = None
_provider = None


def get_repo():
    global _repo
    if _repo is None:
        _repo = make_repo()
        _repo.init_db()
    return _repo


def get_provider():
    global _provider
    if _provider is None:
        _provider = make_provider()
    return _provider


def _caller(user_id: str) -> str:
    """Normalize a caller id.

    A raw '+' in a query string decodes to a space, so "+9198..." arrives as
    " 9198...". Phone numbers are E.164, so restore the '+' rather than making
    every client remember to percent-encode it.
    """
    uid = (user_id or "").strip()
    if uid and uid[0].isdigit() and (user_id or "").startswith(" "):
        return "+" + uid
    return uid


def _iso(v):
    return v if isinstance(v, str) else (v.isoformat() if v else None)


def _usable_name(value) -> str:
    """Return a model-emitted order name when it is suitable for staff UI."""
    name = str(value or "").strip()
    return "" if not name or name.lower() == "no_name_given" else name


def _message_result(message) -> dict:
    """Normalize the structured final result persisted on assistant messages."""
    metadata = message.metadata or {}
    response_fields = metadata.get("response_fields") or {}
    order = metadata.get("order") or response_fields.get("order")
    return {
        "order_ready": bool(metadata.get("order_ready", response_fields.get("order_ready"))),
        "order": order if isinstance(order, dict) else None,
        "order_type": response_fields.get("order_type") or "",
        "name": _usable_name(
            response_fields.get("user_name") or response_fields.get("name")
        ),
    }


def _session_facts(repo, session) -> dict:
    """Read the latest structured name/order emitted within one session."""
    name = ""
    completed = None
    for message in reversed(repo.all_messages(session.session_id)):
        if message.role != "assistant":
            continue
        result = _message_result(message)
        order = result["order"]
        candidate_name = result["name"] or _usable_name(
            order.get("customer_name") if order else ""
        )
        if not name and candidate_name:
            name = candidate_name
        if completed is None and result["order_ready"] and order:
            completed = {
                "event": "order_ready",
                "emitted_at": _iso(message.created_at),
                "idempotency_key": session.session_id,
                "call_uuid": session.session_id,
                "user_id": session.user_id,
                "session_id": session.session_id,
                "order_type": result["order_type"] or order.get("fulfillment") or "pickup",
                "name": candidate_name,
                "channel": "chat",
                "order": order,
            }
        if name and completed is not None:
            break
    if completed is not None and not completed["name"]:
        completed["name"] = name
    return {"name": name, "completed_order": completed}


def _all_completed_orders(repo, limit: int = 200) -> list[dict]:
    orders = []
    for caller in repo.list_callers(limit=200):
        for session in repo.list_sessions(caller["user_id"], limit=50):
            completed = _session_facts(repo, session)["completed_order"]
            if completed:
                orders.append(completed)
    orders.sort(key=lambda item: item.get("emitted_at") or "", reverse=True)
    return orders[:limit]


def _menu_id(category: str, name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", f"{category}-{name}".lower()).strip("-")
    return value or "menu-item"


class ChatIn(BaseModel):
    user_id: str = "default"          # the caller's phone number
    session_id: str | None = None
    message: str
    include_llm_debug: bool = False
    new_session: bool = False
    channel: str = "voice"             # "voice" | "whatsapp" — gates call-only behavior (e.g. disclosure)


@app.get("/health")
def health():
    return {"status": "ok", "storage": config.STORAGE, "model": config.LLM_MODEL}


@app.post("/chat", dependencies=[Depends(require_chat_key)])
def chat(body: ChatIn):
    if not body.message.strip():
        raise HTTPException(400, "message cannot be empty")
    return handle_message(get_repo(), get_provider(),
                          _caller(body.user_id), body.session_id, body.message,
                          include_llm_debug=body.include_llm_debug,
                          new_session=body.new_session, channel=body.channel)


@app.get("/callers", dependencies=[Depends(require_dashboard_key)])
def callers():
    """Distinct phone numbers with activity counts — the dashboard's left rail."""
    repo = get_repo()
    out = []
    for r in repo.list_callers():
        resolved_name = ""
        for session in repo.list_sessions(r["user_id"], limit=50):
            resolved_name = _session_facts(repo, session)["name"]
            if resolved_name:
                break
        out.append({**r, "name": _usable_name(resolved_name),
                    "last_active": _iso(r.get("last_active"))})
    return out


@app.delete("/callers", dependencies=[Depends(require_dashboard_key)])
def delete_caller(user_id: str):
    user_id = _caller(user_id)
    get_repo().delete_user(user_id)
    return {"deleted": user_id}


@app.get("/sessions", dependencies=[Depends(require_dashboard_key)])
def sessions(user_id: str = "default"):
    repo = get_repo()
    user_id = _caller(user_id)
    out = []
    for s in repo.list_sessions(user_id):
        facts = _session_facts(repo, s)
        completed = facts["completed_order"]
        out.append({
            "session_id": s.session_id,
            "title": s.title,
            "message_count": repo.session_message_count(s.session_id),
            "updated_at": _iso(s.updated_at),
            "running_summary": s.running_summary,
            "name": facts["name"],
            "order_type": completed["order_type"] if completed else "",
        })
    return out


@app.get("/orders/recent", dependencies=[Depends(require_dashboard_key)])
def recent_orders(limit: int = 100):
    """Completed structured orders from chat_manager, newest first."""
    return {"orders": _all_completed_orders(get_repo(), max(1, min(limit, 500)))}


@app.get("/menu", dependencies=[Depends(require_dashboard_key)])
def pickup_menu():
    """Read-only pickup menu used by the dashboard.

    Cake and catering intake is manager-led and intentionally has no menu here.
    """
    grouped = defaultdict(list)
    for item in menu_items():
        category = str(item.get("category") or "other")
        grouped[category].append({
            "id": _menu_id(category, str(item.get("name") or "item")),
            "category": category,
            "name": item.get("name") or "Item",
            "price": f"{float(item.get('price') or 0):.2f}",
        })
    sections = [
        {
            "name": category,
            "label": category.replace("_", " ").replace("-", " ").title(),
            "items": items,
        }
        for category, items in sorted(grouped.items())
    ]
    return {
        "takeaway": {
            "sections": sections,
            "category_count": len(sections),
            "item_count": sum(len(section["items"]) for section in sections),
        },
        "catering": {"sections": [], "category_count": 0, "item_count": 0},
        "cakes": {"classes": [], "class_count": 0, "flavor_count": 0, "price_count": 0},
        "read_only": True,
    }


@app.get("/crm/customers", dependencies=[Depends(require_dashboard_key)])
def crm_customers():
    """Customer/order aggregates derived from persisted completed sessions."""
    repo = get_repo()
    orders_by_user = defaultdict(list)
    for record in _all_completed_orders(repo, limit=500):
        orders_by_user[record["user_id"]].append(record)

    customers = []
    for caller in repo.list_callers(limit=200):
        user_id = caller["user_id"]
        records = orders_by_user.get(user_id, [])
        name = ""
        for session in repo.list_sessions(user_id, limit=50):
            name = _session_facts(repo, session)["name"]
            if name:
                break
        history = []
        spend = 0.0
        for record in records:
            order = record["order"]
            total = float(order.get("total") or 0)
            spend += total
            history.append({
                "type": record["order_type"],
                "id": record["session_id"],
                "status": "received",
                "pickup_time": str(order.get("preparation_minutes") or ""),
                "total": total,
                "created_at": record["emitted_at"],
                "items": [
                    {"name": item.get("name") or "Item", "qty": item.get("quantity") or 1}
                    for item in order.get("items") or []
                ],
            })
        customers.append({
            "id": user_id,
            "name": name,
            "phone": user_id,
            "orders": len(records),
            "spend": round(spend, 2),
            "last_order": records[0]["emitted_at"] if records else "",
            "diet": "",
            "address": "",
            "history": history,
        })
    return customers


@app.get("/sessions/{session_id}/messages", dependencies=[Depends(require_dashboard_key)])
def messages(session_id: str):
    return [
        {"seq": m.seq, "role": m.role, "content": m.content,
         "created_at": _iso(m.created_at)}
        for m in get_repo().all_messages(session_id)
    ]


@app.get("/sessions/{session_id}/debug", dependencies=[Depends(require_dashboard_key)])
def session_debug(session_id: str):
    session = get_repo().get_session(session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    return session.metadata.get("llm_debug")


@app.delete("/sessions/{session_id}", dependencies=[Depends(require_dashboard_key)])
def delete(session_id: str):
    get_repo().delete_session(session_id)
    return {"deleted": session_id}


@app.get("/search", dependencies=[Depends(require_dashboard_key)])
def search(user_id: str, q: str):
    """Search a caller's past conversations; returns a preview per hit."""
    hits = get_repo().search_messages(_caller(user_id), q, "", 20)
    return [
        {"session_id": h.session_id, "preview": h.content[:160],
         "created_at": _iso(h.created_at)}
        for h in hits
    ]


@app.get("/staff/search", dependencies=[Depends(require_dashboard_key)])
def staff_search(q: str):
    """Authenticated staff search across caller phone numbers and sessions."""
    query = (q or "").strip()
    if not query:
        return []
    repo = get_repo()
    results = []
    for caller in repo.list_callers(limit=200):
        user_id = caller["user_id"]
        for hit in repo.search_messages(user_id, query, "", 5):
            results.append({
                "user_id": user_id,
                "session_id": hit.session_id,
                "preview": hit.content[:160],
                "created_at": _iso(hit.created_at),
            })
    results.sort(key=lambda hit: hit["created_at"] or "", reverse=True)
    return results[:50]


# ── voice ────────────────────────────────
@app.post("/stt", dependencies=[Depends(require_dashboard_key)])
async def stt(file: UploadFile = File(...)):
    """Speech to text via OpenAI. Used by the browser mic."""
    import tempfile, os
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(await file.read())
    tmp.close()
    try:
        return {"text": get_provider().transcribe(tmp.name)}
    finally:
        os.unlink(tmp.name)


class TTSIn(BaseModel):
    text: str


@app.post("/tts", dependencies=[Depends(require_dashboard_key)])
def tts(body: TTSIn):
    """Text to speech via ElevenLabs. Returns mp3 bytes."""
    from voice.tts import synthesize
    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(503, "ELEVENLABS_API_KEY not configured")
    return Response(content=synthesize(body.text), media_type="audio/mpeg")


# ── dashboard ────────────────────────────
@app.get("/")
def dashboard():
    return FileResponse(WEB / "index.html")


@app.get("/app.js")
def appjs():
    return FileResponse(WEB / "app.js", media_type="application/javascript")


@app.get("/style.css")
def appcss():
    return FileResponse(WEB / "style.css", media_type="text/css")
