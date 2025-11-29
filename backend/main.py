from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Optional, Literal
from pathlib import Path
import asyncio
import time
from openai import OpenAI, RateLimitError
from voice import synthesize_speech
from transcribe import transcribe_file
from prosody import detect_tone

def load_api_key() -> str:
    """
    Load the OpenAI API key from zelda_key.env (same folder as main.py).
    The file should contain ONLY the key on a single line.
    """
    env_path = Path(__file__).with_name("zelda_key.env")
    if not env_path.exists():
        raise RuntimeError(
            f"API key file not found at {env_path}. "
            "Create zelda_key.env with your OpenAI key in it."
        )
    key = env_path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError("zelda_key.env is empty. Put your OpenAI key in it.")
    return key

# Initialize OpenAI client using key from file
client = OpenAI(api_key=load_api_key())

# Audio dir + FastAPI app + static mount
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

# --- Static video clips for Zelda avatar ---
BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "video"
VIDEO_DIR.mkdir(exist_ok=True)

#--- Frontend directory (sibling to backend/) ---
# Project root
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI()
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")
app.mount("/video", StaticFiles(directory=str(VIDEO_DIR)), name="video")
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend",)

# Allow frontend (e.g. index.html opened from file:// or localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for local dev; we can tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    message: str
    mode: Optional[str] = "friendly"
    history: Optional[List[HistoryItem]] = None

class ChatResponse(BaseModel):
    reply: str
    audio_url: Optional[str] = None
    tone: Optional[str] = None
    
@app.get("/")
async def serve_frontend_index():
    """
    Serve the main Zelda frontend page at the root URL.
    """
    index_path = FRONTEND_DIR / "index.html"
    return FileResponse(index_path)
    

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Simple endpoint:
    - Takes your latest message + previous history (optional)
    - Calls OpenAI Chat API as "Zelda"
    - Generates speech audio via voice.synthesize_speech()
    - Returns reply text + audio URL
    """

    # Choose Zelda's personality mode from the request
    mode = (req.mode or "friendly").lower()

    if mode == "therapist":
        system_prompt = (
            "You are Zelda in Therapist Mode. You communicate like a licensed professional therapist: "
            "calm, empathetic, emotionally aware, and validating. "
            "You respond in 3–12 reflective sentences, helping the user feel understood and safe. "
            "Avoid clinical jargon (unless asked) and stay warm and human."
        )
    elif mode == "balanced":
        system_prompt = (
            "You are Zelda in Balanced Mode. You are a supportive friend with the emotional insight of a trained therapist. "
            "Respond briefly (1–4 short sentences) with warmth, clarity, and grounded emotional awareness. "
            "Be kind and understanding without being long-winded."
        )
    else:
        # Default to Friendly mode
        system_prompt = (
            "You are Zelda in Friendly Mode. You are warm, calm, light-hearted, supportive, playful, and kind. "
            "You respond in 1–3 short sentences and focus on making the user feel comfortable and understood. "
            "Avoid deep therapeutic analysis unless the user clearly asks for it."
        )

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    # History is deliberately not replayed to keep Zelda stateless per message.
    # If you ever want to reintroduce context, you can safely re-enable this block:
    if req.history:
        for item in req.history:
            messages.append({"role": item.role, "content": item.content})



    messages.append({"role": "user", "content": req.message})

    try:
        # 1. Chat response
        completion = client.chat.completions.create(
            model="gpt-5-mini",  # fall back to gpt-4.1-mini if not available 
            messages=messages,
            #max_tokens=120,
            #temperature=0.2,
        )
        reply_text = completion.choices[0].message.content.strip()
        tone = detect_tone(reply_text)
    except RateLimitError:
        reply_text = (
            "It looks like the API key I'm using has run out of quota or there's "
            "a billing/quota issue. Once that's sorted, I'll be able to reply normally again."
        )
        return ChatResponse(reply=reply_text, audio_url=None, tone="neutral")
    except Exception as e:
        reply_text = f"Something went wrong talking to the chat model: {e}"
        return ChatResponse(reply=reply_text, audio_url=None, tone="neutral")

    # 2. Generate audio for the reply (separate voice module)
    audio_url = synthesize_speech(reply_text)

    return ChatResponse(reply=reply_text, audio_url=audio_url, tone=tone)
    
@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Accept an audio file (e.g. from the browser) and return a text transcription.
    Uses the helper in transcribe.py.
    """
    try:
        # Ensure we're at the start of the uploaded file
        file.file.seek(0)
        text = transcribe_file(file.file)
        print("Transcribed text:", repr(text))
        return {"text": text}
    except Exception as e:
        print("Transcription error:", e)
        return {"text": ""}

#------------------------------------------------------------------------------
# Background task: periodically delete old audio files for privacy
# ------------------------------------------------------------------------------

AUDIO_TTL_SECONDS = 5 * 60  # 5 minutes; adjust as desired


async def cleanup_audio_loop() -> None:
    """
    Periodically delete audio files older than AUDIO_TTL_SECONDS
    from the /audio directory located next to main.py.
    """
    audio_dir = Path(__file__).with_name("audio")
    audio_dir.mkdir(exist_ok=True)

    while True:
        try:
            now = time.time()
            cutoff = now - AUDIO_TTL_SECONDS

            for mp3_path in audio_dir.glob("*.mp3"):
                try:
                    mtime = mp3_path.stat().st_mtime
                    if mtime < cutoff:
                        print(f"[cleanup] Deleting old audio file: {mp3_path.name}")
                        mp3_path.unlink()
                except Exception as inner_err:
                    print(f"[cleanup] Error deleting {mp3_path}: {inner_err}")
        except Exception as outer_err:
            print("[cleanup] Unexpected error during cleanup loop:", outer_err)

        # Sleep before next cleanup sweep
        await asyncio.sleep(60)


@app.on_event("startup")
async def start_cleanup_task() -> None:
    """
    Start the background cleanup loop when the FastAPI app starts.
    """
    asyncio.create_task(cleanup_audio_loop())
    
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Serve the Zelda PNG as the favicon
    return FileResponse(FRONTEND_DIR / "zelda.PNG")