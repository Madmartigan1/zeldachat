from pathlib import Path
from uuid import uuid4
from openai import OpenAI, RateLimitError
from prosody import format_for_tts

def load_api_key() -> str:
    """
    Load the OpenAI API key from zelda_key.env (same folder as this file).
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


# Separate OpenAI client just for TTS (same key, no problem)
tts_client = OpenAI(api_key=load_api_key())

# Audio directory (same as main.py will use)
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)


def synthesize_speech(text: str) -> str | None:
    """
    Generate speech audio for the given text.

    Returns:
        A relative URL like "/audio/xxxx.mp3" on success,
        or None if something went wrong.
    """
    try:
        # Shape the text for more emotional, natural TTS delivery
        tts_text = format_for_tts(text)
        audio_filename = f"{uuid4().hex}.mp3"
        audio_path = AUDIO_DIR / audio_filename

        speech = tts_client.audio.speech.create(
            model="gpt-4o-mini-tts",
            # "shimmer" is a brighter, more youthful voice
            # You can also try: "nova", "verse", "coral"
            voice="nova",
            input=tts_text,
            # Slightly faster than 1.0 to feel a bit lighter/younger
            speed=0.9,
        )

        # Save MP3 to file
        speech.stream_to_file(str(audio_path))

        # This matches the static mount we'll set up in main.py
        return f"/audio/{audio_filename}"

    except RateLimitError as e:
        print("TTS RateLimitError / quota issue:", e)
        return None
    except Exception as e:
        print("TTS error generating speech:", e)
        return None
