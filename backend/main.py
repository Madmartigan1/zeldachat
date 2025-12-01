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

# ---- Conversation windowing / summarization settings ----
MAX_TURNS_FOR_MODEL = 12  # how many recent messages (user+assistant) to send verbatim
SUMMARY_TURN_THRESHOLD = 20  # only bother summarizing if history is this long or more
SUMMARY_MAX_CHARS_FALLBACK = 1000  # fallback length if summarization fails

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
    
def summarize_history_for_model(history_items: List[HistoryItem]) -> str:
    """
    Summarize older parts of the conversation into a compact form to save tokens,
    similar to how ChatGPT truncates/summarizes long chats.
    """
    if not history_items:
        return ""

    # Turn the history into a simple transcript
    convo_lines = []
    for item in history_items:
        speaker = "User" if item.role == "user" else "Zelda"
        convo_lines.append(f"{speaker}: {item.content}")
    convo_text = "\n".join(convo_lines)

    try:
        completion = client.chat.completions.create(
            model="gpt-5.1",  # you can switch this to a cheaper model later if you want
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise summarizer of a conversation between a user and an AI companion "
                        "named Zelda. Summarize the key facts, themes, and emotional dynamics so far in "
                        "no more than 120 words. Do NOT give advice or continue the conversation. Just summarize."
                    ),
                },
                {
                    "role": "user",
                    "content": convo_text,
                },
            ],
            max_completion_tokens=180,
        )
        summary = (completion.choices[0].message.content or "").strip()
        return summary or convo_text[:SUMMARY_MAX_CHARS_FALLBACK]
    except Exception as e:
        print("[Zelda SUMMARY] Error while summarizing history:", e)
        # Fallback: truncated raw text so we don't lose all context
        return convo_text[:SUMMARY_MAX_CHARS_FALLBACK]


def build_messages_with_window_and_summary(
    system_prompt: str,
    history: Optional[List[HistoryItem]],
    latest_user_message: str,
) -> List[dict]:
    """
    Build the messages list for the chat model:
    - system prompt
    - (optional) summary of older history
    - recent turns verbatim
    - latest user message
    """

    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    history = history or []

    if not history:
        # No prior turns, just add the latest user message
        messages.append({"role": "user", "content": latest_user_message})
        return messages

    # If history is short, we can send it all
    if len(history) <= MAX_TURNS_FOR_MODEL:
        for item in history:
            messages.append({"role": item.role, "content": item.content})
    else:
        # Split into older vs recent
        older = history[:-MAX_TURNS_FOR_MODEL]
        recent = history[-MAX_TURNS_FOR_MODEL:]

        if len(history) >= SUMMARY_TURN_THRESHOLD:
            # Summarize the older portion into a compact system-style note
            summary_text = summarize_history_for_model(older)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Summary of the earlier conversation for context (do NOT repeat verbatim; use it only as background):\n"
                        f"{summary_text}"
                    ),
                }
            )
        else:
            # History isn't that long; we can just keep all of it
            recent = history

        for item in recent:
            messages.append({"role": item.role, "content": item.content})

    # Finally, the latest user message
    messages.append({"role": "user", "content": latest_user_message})
    return messages


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    - Takes the latest message + full history (optional)
    - Calls OpenAI Chat API as "Zelda"
    - Generates speech audio via voice.synthesize_speech()
    - Returns reply text + audio URL + tone
    """

    mode = (req.mode or "friendly").lower()

    if mode == "therapist":
        system_prompt = (
            "You are Zelda in Therapist Mode and your answers are from a psychological standpoint. You are NOT a licensed professional (you can simulate one), "
            "but you sound like a kind, grounded therapist who really cares about the user's feelings.\n\n"
            "STYLE:\n"
            "- Tone: warm, calm, compassionate, and honest.\n"
            "- Replies: about 4–8 short sentences max (avoid long paragraphs).\n"
            "- Use 1–3 numbered points (1., 2., 3.) if they help clarity.\n\n"
            "WHAT TO DO:\n"
            "1. Reflect and validate how the user seems to feel so they feel understood.\n"
            "2. Offer 1–3 short, clear insights about what might be happening emotionally.\n"
            "3. When appropriate, suggest 1–2 small, realistic next steps or coping ideas.\n\n"
            "WHAT TO AVOID:\n"
            "- Long, rambling essays.\n"
            "- Clinical or robotic language.\n"
            "- Minimizing or dismissing the user's feelings.\n"
            "- Claiming to be a doctor or licensed therapist.\n\n"
            "IMPORTANT:\n"
            "- Never return an empty or blank response. Always respond with at least one sentence."
        )
    elif mode == "balanced":
        system_prompt = (
            "You are Zelda in Balanced Mode. You are a supportive friend with the emotional insight of a therapist, "
            "but you keep things short and easy to read.\n\n"
            "STYLE:\n"
            "- Tone: warm, relaxed, and conversational, like a close friend who 'gets it.'\n"
            "- Replies are brief: 2–6 short sentences total.\n"
            "- You can use 1–2 numbered points (1., 2.) if it helps clarity, but keep the structure simple.\n"
            "- Use everyday language and keep explanations lightweight.\n\n"
            "WHAT TO DO:\n"
            "1. Briefly reflect how the user seems to feel so they feel understood.\n"
            "2. Offer one or two clear insights about what might be going on emotionally or psychologically.\n"
            "3. If it fits, end with one gentle, practical suggestion or encouragement.\n\n"
            "WHAT TO AVOID:\n"
            "- Do not write long, detailed analyses (leave that to Therapist Mode).\n"
            "- Do not be clinical or overly serious if the user is just chatting.\n"
            "- Do not ignore their feelings or jump straight to advice without some validation first.\n"
        )
    else:
        # Friendly mode
        system_prompt = (
            "You are Zelda in Friendly Mode. You talk like a laid-back, caring and empathetic friend who is easy to open up to.\n\n"
            "STYLE:\n"
            "- Tone: warm, calm, light-hearted, and a bit playful when it fits.\n"
            "- Keep replies short: 1–3 sentences most of the time.\n"
            "- Focus on comfort, small talk, and emotional support, not deep analysis.\n"
            "- You can use an occasional emoji, but don't overdo it.\n\n"
            "WHAT TO DO:\n"
            "- React naturally to what the user says: empathize, joke lightly, or be encouraging.\n"
            "- If the user is playful or mildly flirty, you may respond with light, wholesome teasing.\n"
            "- If the user starts going deep or heavy, be kind and supportive, but save detailed psychology for Therapist Mode.\n\n"
            "WHAT TO AVOID:\n"
            "- Do not give long explanations or structured breakdowns.\n"
            "- Do not be sexual, inappropriate, or cross personal boundaries.\n"
            "- Do not sound like a clinician; you're just a friendly Zelda hanging out.\n"
        )

    # Build messages with ChatGPT-style windowing/summarization:
    # - older turns summarized (if long)
    # - recent turns sent verbatim
    messages = build_messages_with_window_and_summary(
        system_prompt=system_prompt,
        history=req.history,
        latest_user_message=req.message,
    )


    try:
        completion = client.chat.completions.create(
            model="gpt-5.1",  # or gpt-4.1-mini if you want cheaper
            messages=messages,
            max_completion_tokens=300,
            #temperature=0.4,
        )

        choice = completion.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        raw_content = choice.message.content
        reply_text = (raw_content or "").strip()

        # Debug: see what finish_reason is when things go weird
        print(
            f"[Zelda DEBUG] mode={mode}, finish_reason={finish_reason}, "
            f"reply_len={len(reply_text)}, raw_content={repr(raw_content)}"
        )
        
                # If we got nothing back, try a simpler backup call
        if not reply_text:
            print("[Zelda DEBUG] Empty primary reply_text, retrying with simplified prompt...")

            # Simple backup prompt – but still with recent context so memory feels consistent
            if mode == "therapist":
                backup_system = (
                    "You are Zelda, a kind, grounded listener. "
                    "The user just shared something with you. "
                    "Reply in a warm, concise way in about 4–8 short sentences."
                )
            elif mode == "balanced":
                backup_system = (
                    "You are Zelda, a supportive friend. "
                    "Reply briefly (3–6 sentences) in a clear, encouraging way."
                )
            else:
                backup_system = (
                    "You are Zelda, a warm and friendly AI companion. "
                    "Reply in 1–3 sentences, casual and kind."
                )

            # Build a short transcript of the last few turns so the backup
            # still “remembers” what you were talking about.
            if req.history:
                recent = req.history[-12:]  # last 6 turns (you can tweak this)
                convo_lines = []
                for item in recent:
                    speaker = "User" if item.role == "user" else "Zelda"
                    convo_lines.append(f"{speaker}: {item.content}")
                recent_context = (
                    "Here is the recent conversation between the user and Zelda:\n"
                    + "\n".join(convo_lines)
                    + "\n\nNow the user says:\n"
                    + req.message
                )
            else:
                recent_context = req.message

            backup_messages = [
                {"role": "system", "content": backup_system},
                {"role": "user", "content": recent_context},
            ]

            backup_completion = client.chat.completions.create(
                model="gpt-5.1",
                messages=backup_messages,
                max_completion_tokens=300,
            )

            backup_choice = backup_completion.choices[0]
            backup_finish_reason = getattr(backup_choice, "finish_reason", None)
            backup_raw = backup_choice.message.content
            reply_text = (backup_raw or "").strip()

            print(
                f"[Zelda DEBUG] backup mode={mode}, finish_reason={backup_finish_reason}, "
                f"reply_len={len(reply_text)}"
            )


        tone = detect_tone(reply_text)

    except RateLimitError:
        reply_text = (
            "It looks like the API key I'm using has run out of quota or there's "
            "a billing or quota issue. Once that's sorted, I'll be able to reply normally again."
        )
        tone = "neutral"
        return ChatResponse(reply=reply_text, audio_url=None, tone=tone)

    except Exception as e:
        reply_text = f"Something went wrong talking to the chat model: {e}"
        tone = "neutral"
        return ChatResponse(reply=reply_text, audio_url=None, tone=tone)

    # Generate audio for the reply
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