# Customer audio debug logging

Implemented locally: save customer audio from the existing incoming WebSocket
stream (selected option 1), then play/download it beside that turn's transcript
in the same Chat Manager conversation window. This does not call Plivo's
recording API and does not enable full-call recording.

## Data path

1. The gateway's single stream reader copies inbound 8 kHz mono mu-law frames.
   Capture is bounded to 60 seconds / 480,000 bytes per turn and 3,000 frames.
   Frame timestamps/sequences are retained when provided. Timestamp gaps and
   truncation mark the clip incomplete; no missing audio is invented.
2. A recording ID and the raw bytes accompany that turn's normal `/chat`
   request. No separate transcription or additional carrier connection occurs.
3. Chat Manager resolves the owned session, writes the clip under persistent
   `/data/customer_audio`, and saves a recording reference in the exact user
   message's metadata before invoking the LLM. SQLite, Mongo and memory storage
   already support message metadata. No database schema migration is required.
4. `/sessions/{id}/messages` returns the audio reference. The same user bubble
   offers Load audio, a native player with seek/pause, Download WAV, Download
   original audio, and Download diagnostics. Fetching audio uses the existing
   same-origin access path. Switching calls releases loaded Blob URLs.
5. `/sessions/{id}/audio/{recording_id}` checks API authorization, session
   existence, and the message's recording ID. It returns a decoded PCM WAV by
   default, or original `.mulaw` / diagnostic `.json` files on request.

The WAV is a playback derivative, not the original wire bytes. The manifest
includes the original transcript, raw SHA-256, provider/model, configured hints,
carrier/call ID, duration, frame details, capture timing and expiry. Configured
hints do not imply every STT provider supports those hints.

## Debug controls and storage

`DEBUG_CUSTOMER_AUDIO=false` by default. Enable it on the gateway and set
`DEBUG_AUDIO_CALLERS` to comma-separated E.164 test caller numbers. The supplied
installer prompts for those numbers and enables only those callers. It preserves
carrier, recognizer and hints settings. Both carriers remain selectable; no
carrier or STT fallback has been added.

Raw audio and manifests expire after seven days, with hourly cleanup while Chat
Manager runs and an expiry check on access. Capture-time cleanup also enforces a
512 MiB directory quota. Deleting a call deletes its recordings; deleting a
caller deletes recordings for that caller's sessions. Normal TTS hangup cleanup
does not touch customer recordings. Disk/capture failures leave the text flow
working and show audio as unavailable rather than failing the order.

The audio route inherits the existing staff dashboard's access model. The
application does not add a staff login. If Nginx injects the backend key for
anonymous visitors, those visitors also have dashboard/audio access; the
existing staff ingress must control who can open the site. The installer
requires a configured backend API key and persistent `/data` storage.

## Repeatable recognizer testing

Download the original `.mulaw` and diagnostics `.json`. The gateway provides
`scripts/replay_customer_audio.py clip.mulaw --provider deepgram --hints-file clip.json`.
Run it in the gateway environment so it uses configured credentials. Choose
assemblyai, deepgram, sarvam or elevenlabs explicitly; each run makes billed
provider requests and never invokes the brain, order creation or printers.

Replay preserves source bytes and reports their hash. It sends 20 ms chunks
and adds five seconds of explicitly synthetic trailing silence for endpointing.
It uses the selected adapter's current model/settings, optionally replacing
hints with the saved snapshot. It is a reproducible audio test, not an exact
reconstruction of original network timing or post-conversion provider chunks.
Provider failure produces a failed result without fallback. Compare the returned
text against the original transcript and what you hear in the player.

## Boundaries

- New recorded calls only; existing calls have no retroactive clips.
- Only speech received while the incoming stream is listening is captured.
  Speech during assistant playback or before stream start is absent.
- Plivo-native GetInput does not expose this WebSocket stream and cannot use
  this recording/replay path. External STT selection is preserved.
- Only turns with a transcript submitted to Chat Manager have persisted clips.
  Silent turns, failed STT turns, and calls that never reach `/chat` do not yet
  have a separate audio timeline.
- In-UI provider reruns, reference-text editing, WER scoring, provider send-boundary
  capture and a full latency waterfall remain future extensions. Download and
  command-line replay are available now.
- No production restart or real phone-call verification has been performed by
  this local implementation task. Use the one-shot installer between calls,
  then make a test call and check playback in the same conversation window.

## Validation

Automated checks cover bounded byte capture, call-turn association, the synthetic
opening greeting having no clip, SQLite persistence, API authorization,
wrong-session access, WAV decoding, expiry/deletion, and installer rollback.
Live Deepgram and AssemblyAI testing captured synthetic speech and replayed
the identical saved bytes successfully. AssemblyAI used the local 100 menu hints. These checks establish the capture/replay path; they do not
establish Kerala menu transcription accuracy on a real telephone call.

## References

- [Plivo audio streaming protocol](https://www.plivo.com/docs/voice-agents/audio-streaming/concepts/audio-streaming-reference)
- [AssemblyAI keyterms format](https://www.assemblyai.com/docs/voice-agents/best-practices)
