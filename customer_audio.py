"""Private per-turn debug artifacts. Raw mu-law is preserved; WAV is a derivative."""
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import time
import uuid
import wave

MAX_BYTES = 480000  # 60 seconds of 8kHz mono mu-law
RETENTION = 7 * 86400


def directory():
    return Path(os.getenv("CUSTOMER_AUDIO_DIR", "/data/customer_audio"))


def cleanup():
    cutoff = time.time() - RETENTION
    for path in directory().glob("*.*"):
        if path.suffix in {".json", ".mulaw"} and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def save(payload, session_id, transcript=""):
    if not payload:
        return None
    try:
        encoded = payload.get("mulaw_base64", "")
        if len(encoded) > 640000:
            raise ValueError("clip too large")
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > MAX_BYTES or payload.get("sample_rate") != 8000:
            raise ValueError("unsupported clip")
        if payload.get("codec") not in {"audio/x-mulaw", "mulaw"}:
            raise ValueError("unsupported codec")
        folder = directory()
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        cleanup()
        # Quota prevents debug data exhausting the disk (default 512 MiB).
        used = sum(p.stat().st_size for p in folder.glob("*.*"))
        if used + len(raw) + 20000 > 512 * 1024 * 1024:
            raise ValueError("audio quota exceeded")
        rid = uuid.uuid4().hex
        meta = {k: payload[k] for k in ("carrier", "provider", "model", "hints", "codec",
                "sample_rate", "complete", "frames", "elapsed_ms", "call_id", "frame_info") if k in payload}
        meta.update(id=rid, utterance_id=payload.get("id"), session_id=session_id,
                    duration_seconds=len(raw)/8000, sha256=hashlib.sha256(raw).hexdigest(),
                    expires_at=time.time()+RETENTION, source="inbound_stream", original_transcript=transcript)
        manifest = json.dumps(meta).encode()
        if len(manifest) > 400000 or used + len(raw) + len(manifest) > 512 * 1024 * 1024:
            raise ValueError("audio quota exceeded")
        for suffix, data in (("mulaw", raw), ("json", manifest)):
            path = folder / f"{rid}.{suffix}"
            with path.open("xb") as f:
                os.chmod(path, 0o600)
                f.write(data)
        return {"id": rid, "duration_seconds": meta["duration_seconds"],
                "complete": bool(meta.get("complete")), "expires_at": meta["expires_at"]}
    except Exception:
        logging.getLogger(__name__).warning("Customer audio unavailable; continuing text turn")
        return {"status": "unavailable"}


def read(session_id, rid):
    if not re.fullmatch(r"[0-9a-f]{32}", rid):
        raise FileNotFoundError()
    folder = directory()
    meta = json.loads((folder / f"{rid}.json").read_text())
    if meta["session_id"] != session_id:
        raise FileNotFoundError()
    if meta["expires_at"] < time.time():
        for suffix in ("json", "mulaw"):
            (folder / f"{rid}.{suffix}").unlink(missing_ok=True)
        raise FileNotFoundError()
    return meta, (folder / f"{rid}.mulaw").read_bytes()


def wav_bytes(raw):
    # ITU G.711 mu-law decode, no resampling/no normalization.
    import struct
    pcm = bytearray()
    for byte in raw:
        value = (~byte) & 255
        magnitude = (((value & 15) << 3) + 132) << ((value >> 4) & 7)
        sample = 132 - magnitude if value & 128 else magnitude - 132
        pcm.extend(struct.pack("<h", sample))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(pcm)
    return output.getvalue()


def delete_session(session_id):
    for path in directory().glob("*.json"):
        try:
            if json.loads(path.read_text()).get("session_id") == session_id:
                path.with_suffix(".mulaw").unlink(missing_ok=True)
                path.unlink(missing_ok=True)
        except (OSError, ValueError):
            continue
