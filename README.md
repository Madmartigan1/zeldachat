# ZeldaChat 🧠
<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688.svg" />
  <img src="https://img.shields.io/badge/OpenAI-API-412991.svg" />
  <img src="https://img.shields.io/badge/Frontend-HTML%2FJS-orange.svg" />
  <img src="https://img.shields.io/badge/Status-Experimental-yellow.svg" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" />
</p>
<p align="center">
  <img src="frontend/calm.png" alt="Zelda avatar" width="150"
       style="border-radius: 50%; margin-right: 20px;" />
  <img src="https://img.shields.io/badge/AI%20Avatar-Real--Time%20Voice%20&%20Video-blue?style=for-the-badge" />
</p>

A local, browser-based chat UI wired to a small FastAPI backend that talks to OpenAI.

It gives you:

- A friendly “Zelda” persona using `gpt-4.1-mini` for chat.
- Natural-sounding TTS using `gpt-4o-mini-tts` (voice: `nova`) with prosody shaping so it feels more alive.
- Whisper-based speech-to-text so you can talk to Zelda via microphone instead of just typing.
- A simple avatar front-end (PNG + SadTalker MP4 clips) that reacts in sync with the audio (as best as pre-rendered video allows).

---

## 🌐 Project Structure

The repo is intentionally minimal:

```
├── backend/
│ ├── main.py
│ ├── voice.py
│ ├── prosody.py
│ ├── transcribe.py
│ ├── zelda_key.env # your local API key (ignored)
│ ├── audio/ # generated audio (ignored)
│ └── video/ # pre-generated reaction videos
├── frontend/
│ ├── index.html
│ └── zelda.PNG
```

- `main.py` – FastAPI app exposing:
  - `POST /chat` – chat endpoint returning text + `audio_url` + `tone`
  - `POST /transcribe` – transcription endpoint for microphone audio
  - Static `/audio` mount for generated MP3 TTS files
- `voice.py` – TTS helper using OpenAI `gpt-4o-mini-tts` with the `nova` voice and prosody shaping via `prosody.py`.
- `prosody.py` – detects emotional tone of replies and reshapes text for more natural speech delivery, plus exposes `detect_tone()` used by the backend.
- `transcribe.py` – audio transcription via Whisper (`whisper-1`).
- `index.html` – the front-end chat UI with:
  - Typing box + history
  - Mic button (records audio, calls `/transcribe`)
  - “Play Zelda’s voice” toggle
  - Zelda avatar (PNG + pre-generated SadTalker MP4 clips)
- `audio/` – auto-created folder for generated MP3 files (served at `/audio/...`).
- `video/` – (optional) SadTalker MP4 clips used by the avatar (e.g. `zelda_happy.mp4`, `zelda_neutral.mp4`, etc.).
- `zelda_key.env` – **not committed**: a single-line file containing your OpenAI API key, read by both `main.py` and `voice.py`.

---

## ✨ Features

- 🗣️ **Conversational AI** using `gpt-4.1-mini`
- 🔊 **Natural Text-to-Speech** via `gpt-4o-mini-tts`
- 🎤 **Speech-to-Text** using Whisper
- 🎭 **Emotion-based avatar reactions**
- 🌐 Pure **local HTML/JS frontend**
- ⚡ Lightweight **FastAPI** backend (`localhost:8000`)

---

## 🔧 Requirements

- Python **3.11+** (3.10 will likely work, but 3.11 is recommended).
- An OpenAI API key with access to:
  - `gpt-4.1-mini` (chat)
  - `gpt-4o-mini-tts` (TTS)
  - `whisper-1` (STT)
- A modern browser (Chrome, Brave, etc.) with microphone access.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Add your API key

Create a file in /backend named: zelda_key.env and copy/paste your OpenAI key inside


### 3. Load the backend

```
cd backend
uvicorn main:app --reload
```

### 4. Start the frontend

Open frontend/index.html with your browser (Chrome recommended)

---

## 🤝 Contributing 
Pull requests welcome. This is an evolving personal project; improvements and ideas are appreciated. 

--- 

## ⭐ Acknowledgements 

Built with: 
- Python / FastAPI 
- OpenAI APIs 
- HTML / JavaScript 
- Videos generated with SadTalker: https://github.com/OpenTalker/SadTalker
 
 






