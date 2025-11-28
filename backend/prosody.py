"""
prosody.py

Text shaping utilities to make TTS sound more emotional and natural.

We do NOT change the text sent back to the UI, only the text fed into TTS.
"""

from __future__ import annotations
import re

TONE_EXCITED      = "excited"
TONE_NEUTRAL      = "neutral"
TONE_HAPPY        = "happy"
TONE_SYMPATHETIC  = "sympathetic"
TONE_BUMMED       = "bummed"
TONE_REASSURING   = "reassuring"
TONE_ENCOURAGING  = "encouraging"
TONE_PLAYFUL      = "playful"
TONE_INTRIGUED    = "intrigued"
TONE_CAUTION      = "caution"


def detect_tone(text: str) -> str:
    """
    Heuristic tone detection based on Zelda's *reply* text.

    Returns one of:
      'bummed', 'caution', 'encouraging', 'excited', 'happy',
      'intrigued', 'neutral', 'playful', 'reassuring', 'sympathetic'
    which maps 1:1 to your SadTalker clips.
    """
    if not text:
        return TONE_NEUTRAL

    t = text.lower()

    # --- strong negative / empathetic vibes -> bummed / sympathetic ---
    sad_keywords = [
        "i'm sorry", "i am sorry", "that sounds really hard",
        "that sounds tough", "i know this is hard",
        "i know this is tough", "i can see why", "i understand this is",
        "it makes sense you feel", "i get why you feel",
    ]
    if any(k in t for k in sad_keywords):
        # When Zelda is clearly validating pain, use sympathetic
        return TONE_SYMPATHETIC

    # Things like "that sucks", "that's rough" – more "bummed" tone.
    bummed_keywords = [
        "that really sucks", "that sucks", "that's rough", "that’s rough",
        "that’s not fair", "that is not fair",
    ]
    if any(k in t for k in bummed_keywords):
        return TONE_BUMMED

    # --- reassurance / gentle support ---
    reassuring_keywords = [
        "don't worry", "do not worry",
        "you're not alone", "you are not alone",
        "it's okay to", "it’s okay to",
        "it's ok to", "it’s ok to",
        "it's understandable", "it’s understandable",
        "you're doing your best", "you are doing your best",
    ]
    if any(k in t for k in reassuring_keywords):
        return TONE_REASSURING

    # --- encouragement / hype but calm ---
    encouraging_keywords = [
        "you've got this", "you got this",
        "i believe in you", "i’m proud of you", "i am proud of you",
        "keep going", "keep at it",
        "this is a great step", "this is a good step",
        "you’re doing great", "you're doing great",
    ]
    if any(k in t for k in encouraging_keywords):
        return TONE_ENCOURAGING

    # --- happy / upbeat ---
    happy_keywords = [
        "that's great", "that’s great",
        "that's awesome", "that’s awesome",
        "that's fantastic", "that’s fantastic",
        "i'm glad", "i am glad",
        "i'm happy for you", "i am happy for you",
        "congratulations", "congrats",
    ]
    if any(k in t for k in happy_keywords):
        return TONE_HAPPY

    # --- playful / light ---
    playful_keywords = [
        "haha", "lol", "just kidding",
        "couldn’t resist", "couldn't resist",
        "little bit cheeky", "let's have some fun", "let’s have some fun",
    ]
    if any(k in t for k in playful_keywords):
        return TONE_PLAYFUL

    # --- intrigued / curious ---
    intrigued_keywords = [
        "i'm curious", "i am curious",
        "interesting question", "that's interesting", "that’s interesting",
        "let's unpack", "let’s unpack",
        "i wonder", "makes me wonder",
    ]
    if any(k in t for k in intrigued_keywords):
        return TONE_INTRIGUED

    # --- caution / safety vibes ---
    caution_keywords = [
        "be careful", "you’ll want to be careful", "you will want to be careful",
        "this might be risky", "this could be risky",
        "i’d strongly recommend", "i would strongly recommend",
        "i’d avoid", "i would avoid",
        "it’s important to", "it's important to",
    ]
    if any(k in t for k in caution_keywords):
        return TONE_CAUTION

    # --- excited / high-energy positive ---
    excited_keywords = [
        "this is huge", "i'm so excited", "i am so excited",
        "this is amazing", "i'm really excited", "i am really excited",
        "this is incredible", "that’s incredible", "that's incredible",
        "this is insane", "that's insane", "that’s insane",
    ]
    if any(k in t for k in excited_keywords):
        return TONE_EXCITED

    # Fallback
    return TONE_NEUTRAL



def _split_sentences(text: str) -> list[str]:
    """
    Very simple sentence splitter using punctuation.
    Not perfect, but good enough for shaping TTS.
    """
    # Split on ., ?, ! but keep them attached to the sentence
    parts = re.split(r"([.?!])", text)
    sentences: list[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        if part in ".?!":
            current += part
            sentences.append(current.strip())
            current = ""
        else:
            if current:
                current += part
            else:
                current = part

    if current.strip():
        sentences.append(current.strip())

    # Fallback: if we somehow got nothing, just return original
    if not sentences:
        return [text.strip()]

    return sentences


def _soften_existing_name(sentences: list[str], tone: str) -> list[str]:
    
    if tone != TONE_SYMPATHETIC:
        return sentences

    softened: list[str] = []

    for idx, s in enumerate(sentences):
        # Only soften the first sentence; later ones can stay as-is
        if idx == 0:
            # Match the user's name
            m = re.match(r"^([A-Z][a-z]{1,20})([, ]+)(.*)$", s)
            if m:
                name, sep, rest = m.groups()
                rest = rest.lstrip()
                if rest:
                    s = f"{name}... {rest}"
                else:
                    s = f"{name}..."
        softened.append(s)

    return softened


def format_for_tts(text: str) -> str:
    """
    Take the plain reply text and reshape it a bit so TTS sounds more expressive:
      - shorter lines
      - gentle pauses with ellipses
      - extra line breaks for important / emotional sentences

    We try to keep meaning intact while giving TTS more structure to work with.
    """
    text = text.strip()
    if not text:
        return text

    tone = detect_tone(text)
    sentences = _split_sentences(text)

    # First pass: gently soften any existing name at the start (sympathetic only)
    sentences = _soften_existing_name(sentences, tone)

    shaped_lines: list[str] = []

    if tone in (TONE_SYMPATHETIC, TONE_BUMMED):
        # One sentence per line, with extra spacing and gentle ellipses
        for i, s in enumerate(sentences):
            lower_s = s.lower()
            if any(word in lower_s for word in ["sorry", "hard", "tough", "understand", "alone", "worried"]):
                if not s.endswith("..."):
                    s = s + "..."
            shaped_lines.append(s)
            # Add blank line every 1–2 sentences for extra breathing room
            if i % 2 == 1:
                shaped_lines.append("")

    elif tone in (TONE_ENCOURAGING, TONE_HAPPY, TONE_REASSURING, TONE_PLAYFUL, TONE_EXCITED):
        # Group short phrases to keep momentum but add mild pauses
        buffer: list[str] = []
        for s in sentences:
            buffer.append(s)
            joined = " ".join(buffer)
            if len(joined) > 80:
                shaped_lines.append(joined)
                buffer = []
        if buffer:
            shaped_lines.append(" ".join(buffer))

        # Add a soft closing "lift" depending on the upbeat tone
        if shaped_lines:
            last = shaped_lines[-1]
            if tone in (TONE_ENCOURAGING, TONE_REASSURING, TONE_PLAYFUL):
                if not last.endswith(("!", "…", "...")):
                    last = last + "..."
            elif tone in (TONE_HAPPY, TONE_EXCITED):
                # Excited/happy tends to land on a clear exclamation
                if not last.endswith("!"):
                    last = last + "!"
            shaped_lines[-1] = last

    elif tone == TONE_CAUTION:
        # Slightly slower, more segmented delivery
        for s in sentences:
            shaped_lines.append(s)
            shaped_lines.append("")  # blank line after each caution sentence

    else:
        # Neutral: just join into reasonable-length lines
        buffer: list[str] = []
        for s in sentences:
            buffer.append(s)
            joined = " ".join(buffer)
            if len(joined) > 100:
                shaped_lines.append(joined)
                buffer = []
        if buffer:
            shaped_lines.append(" ".join(buffer))

    # Clean up leading/trailing blank lines
    while shaped_lines and not shaped_lines[0].strip():
        shaped_lines.pop(0)
    while shaped_lines and not shaped_lines[-1].strip():
        shaped_lines.pop()

    # Join with double newlines to hint at paragraph-level pauses
    out = "\n\n".join(shaped_lines) if shaped_lines else text

    # Normalize ellipses so TTS is less likely to say "dot dot dot"
    # Replace "..." with a single ellipsis character
    out = out.replace("...", "…")

    # Clean up any odd " ." spacing
    out = re.sub(r"\s+\.", ".", out)

    return out

