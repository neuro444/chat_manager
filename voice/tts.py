"""ElevenLabs text-to-speech.

Uses the REST endpoint directly so the SDK is not a hard dependency.
"""
import httpx

import config

_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synthesize(text: str, voice_id: str | None = None) -> bytes:
    voice = voice_id or config.ELEVENLABS_VOICE_ID
    if not voice:
        raise RuntimeError("No ElevenLabs voice id configured (ELEVEN_VOICE)")
    resp = httpx.post(
        _URL.format(voice_id=voice),
        headers={"xi-api-key": config.ELEVENLABS_API_KEY,
                 "accept": "audio/mpeg"},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content
