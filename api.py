"""HTTP API + staff dashboard.

Identity model: there is no login. `user_id` IS the caller's phone number,
supplied by the voice channel (browser mic today, telephony webhook later).
Staff read the dashboard; callers never see a screen.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import config
from providers import make_provider
from service import handle_message
from storage import make_repo

app = FastAPI(title="Chat Manager — Phone Ordering")
WEB = Path(__file__).parent / "web"

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


class ChatIn(BaseModel):
    user_id: str = "default"          # the caller's phone number
    session_id: str | None = None
    message: str
    include_llm_debug: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "storage": config.STORAGE, "model": config.LLM_MODEL}


@app.post("/chat")
def chat(body: ChatIn):
    if not body.message.strip():
        raise HTTPException(400, "message cannot be empty")
    return handle_message(get_repo(), get_provider(),
                          _caller(body.user_id), body.session_id, body.message,
                          include_llm_debug=body.include_llm_debug)


@app.get("/callers")
def callers():
    """Distinct phone numbers with activity counts — the dashboard's left rail."""
    repo = get_repo()
    out = []
    for r in repo.list_callers():
        user = repo.get_user(r["user_id"])
        out.append({**r, "name": user.name if user else "",
                    "last_active": _iso(r.get("last_active"))})
    return out


@app.get("/sessions")
def sessions(user_id: str = "default"):
    repo = get_repo()
    user_id = _caller(user_id)
    return [
        {
            "session_id": s.session_id,
            "title": s.title,
            "message_count": repo.session_message_count(s.session_id),
            "updated_at": _iso(s.updated_at),
            "running_summary": s.running_summary,
        }
        for s in repo.list_sessions(user_id)
    ]


@app.get("/sessions/{session_id}/messages")
def messages(session_id: str):
    return [
        {"seq": m.seq, "role": m.role, "content": m.content,
         "created_at": _iso(m.created_at)}
        for m in get_repo().all_messages(session_id)
    ]


@app.delete("/sessions/{session_id}")
def delete(session_id: str):
    get_repo().delete_session(session_id)
    return {"deleted": session_id}


@app.get("/search")
def search(user_id: str, q: str):
    """Search a caller's past conversations; returns a preview per hit."""
    hits = get_repo().search_messages(_caller(user_id), q, "", 20)
    return [
        {"session_id": h.session_id, "preview": h.content[:160],
         "created_at": _iso(h.created_at)}
        for h in hits
    ]


# ── voice ────────────────────────────────
@app.post("/stt")
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


@app.post("/tts")
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
