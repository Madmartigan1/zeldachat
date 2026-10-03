# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ZeldaChat: a voice-enabled AI companion. A FastAPI backend (`backend/`) wraps OpenAI chat, TTS, and transcription; a single-file HTML/JS frontend (`frontend/index.html`) shows chat, records mic audio, plays TTS, and swaps pre-rendered SadTalker avatar clips based on the reply's emotional tone.

Product goal: a realistic, emotionally expressive avatar face whose persona balances empathy with tough love. Changes to prompts, tone detection, prosody, or avatar clips should serve that.

## Commands

All backend commands run from `backend/` because modules import each other as top-level names (`from voice import ...`).

```bash
pip install -r requirements.txt          # from repo root

cd backend
uvicorn main:app --reload                # local dev on :8000
uvicorn main:app --host 0.0.0.0 --port 9877   # for remote access, then: ngrok http 9877
```

The frontend is served by the backend at `/frontend/` (`/` redirects there so relative asset paths in `index.html` resolve), or can be opened directly as `file://.../frontend/index.html`. In the `file://` case it hard-codes `http://127.0.0.1:8000` as the API base; otherwise it uses `window.location.origin`.

There is no test suite, linter, or build step.

## Setup requirement

`backend/zelda_key.env` must contain only the raw OpenAI API key on one line (not `KEY=value` format). It is read at **import time** by `main.py`, `voice.py`, and `transcribe.py` (via `voice.load_api_key`), so importing any backend module without it raises. The file is gitignored and untracked (it holds a real key locally) — never force-add or commit it.

## Architecture

**Request flow for `POST /chat`** (`backend/main.py`):
1. Frontend sends `{message, mode, history}`. The client owns conversation state; the backend is stateless and receives the full `history` array every request.
2. `mode` (`friendly` | `therapist` | `balanced`) selects one of three inline system prompts in `chat()`.
3. `build_messages_with_window_and_summary` sends the last `MAX_TURNS_FOR_MODEL` messages verbatim; once history reaches `SUMMARY_TURN_THRESHOLD`, older turns are summarized by an extra model call and injected as a system message.
4. If the model returns empty content, a second call is made with a simplified per-mode backup prompt plus a flattened transcript of recent turns.
5. `prosody.detect_tone(reply)` picks a tone label via keyword matching (ordered checks; first match wins).
6. `voice.synthesize_speech` runs `prosody.format_for_tts` (reshapes text with line breaks/ellipses per tone — TTS input only, the UI gets the original text), writes an MP3 to `backend/audio/`, and returns `/audio/<uuid>.mp3`.
7. Response: `{reply, audio_url, tone}`. Errors are returned as a normal reply string with `tone="neutral"`, not HTTP errors.

**Tone contract** — the tone strings are a cross-file contract: `prosody.py` `TONE_*` constants ↔ `toneToVideo` map in `index.html` ↔ `backend/video/zelda_<tone>.mp4`. Adding/renaming a tone requires updating all three. (Note: `setAvatarTone` in `index.html` uses a separate, older set of CSS class names like `tone-celebratory`/`tone-warm_playful` that mostly don't match current tones.)

**`POST /transcribe`** accepts a webm upload and calls `transcribe.transcribe_file`; failures return `{"text": ""}`.

**Static mounts**: `/audio` (generated MP3s), `/video` (avatar clips), `/frontend`. A startup background task deletes MP3s in `backend/audio/` older than `AUDIO_TTL_SECONDS` (5 min).

**Models in use** (code is the source of truth; README model names are outdated): chat and summarization `gpt-5.1` with `max_completion_tokens`; TTS `gpt-4o-mini-tts` voice `nova`; STT `gpt-4o-transcribe`. Each module creates its own `OpenAI` client.
