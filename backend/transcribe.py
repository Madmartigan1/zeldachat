from pathlib import Path
from openai import OpenAI, RateLimitError
from voice import load_api_key  # reuse the same key loader as voice.py
import io

# Separate OpenAI client just for transcription (same key, no problem)
stt_client = OpenAI(api_key=load_api_key())


def transcribe_file(file_obj) -> str:
    """
    Transcribe an audio file-like object using OpenAI Whisper.

    Args:
        file_obj: A file-like object (e.g. UploadFile.file from FastAPI).

    Returns:
        The transcribed text (may be empty string on error).
    """
    try:
        # Read all bytes from the uploaded file
        data = file_obj.read()
        print("Received audio bytes:", len(data))

        if not data:
            return ""

        # Wrap bytes in a BytesIO and give it a proper name so the client
        # knows it's a webm audio file.
        audio_file = io.BytesIO(data)
        audio_file.name = "speech.webm"

        transcript = stt_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        text = getattr(transcript, "text", "") or ""
        return text.strip()
    except RateLimitError as e:
        print("Transcription RateLimitError / quota issue:", e)
        return ""
    except Exception as e:
        print("Transcription error:", e)
        return ""
