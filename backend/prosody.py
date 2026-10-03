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

# One-line meaning per tone, used to tell the chat model which tags it may pick.
# Keys must match the frontend's toneToVideo map and backend/video/zelda_<tone>.mp4.
TONE_DESCRIPTIONS = {
    TONE_NEUTRAL:     "calm, matter-of-fact",
    TONE_HAPPY:       "glad, warm, pleased for the user",
    TONE_EXCITED:     "high-energy, thrilled",
    TONE_PLAYFUL:     "teasing, joking, light",
    TONE_INTRIGUED:   "curious, interested, thinking it over",
    TONE_ENCOURAGING: "motivating, cheering the user on, firm but supportive",
    TONE_REASSURING:  "soothing, calming worries",
    TONE_SYMPATHETIC: "validating pain, gentle compassion",
    TONE_BUMMED:      "disappointed or sad on the user's behalf",
    TONE_CAUTION:     "warning, serious, being straight about a risk or a hard truth",
}
TONES = set(TONE_DESCRIPTIONS)

# A bracketed tag at the very start, e.g. "[happy]", "**[Happy]**", "[tone: happy]",
# optionally followed by the reply on the same line.
_TONE_BRACKET_RE = re.compile(r"^[\s*_`]*\[\s*(?:tone\s*:\s*)?([a-z]+)\s*\][*_`]*[ \t]*", re.IGNORECASE)
# A first line that is only "Tone: happy" or "happy".
_TONE_LINE_RE = re.compile(r"^[\s*_`]*(?:tone\s*:\s*)?([a-z]+)[\s*_`]*$", re.IGNORECASE)


def split_tone_tag(text: str) -> tuple[str | None, str]:
    """
    If the model's reply starts with a valid tone tag, return
    (tone, text_without_tag). Otherwise return (None, text) unchanged.
    """
    if not text:
        return None, text
    stripped = text.lstrip()

    m = _TONE_BRACKET_RE.match(stripped)
    if m:
        # Drop the tag even if the tone is unknown, so it never reaches the UI.
        tone = m.group(1).lower()
        return (tone if tone in TONES else None), stripped[m.end():].strip()

    first, _, rest = stripped.partition("\n")
    m = _TONE_LINE_RE.match(first)
    if m and m.group(1).lower() in TONES:
        return m.group(1).lower(), rest.strip()

    return None, text


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
            # Match the user's name; require a comma ("Alex, ...") so ordinary
            # first words like "That sounds..." are not treated as names
            m = re.match(r"^([A-Z][a-z]{1,20})(,\s*)(.*)$", s)
            if m:
                name, sep, rest = m.groups()
                rest = rest.lstrip()
                if rest:
                    s = f"{name}... {rest}"
                else:
                    s = f"{name}..."
        softened.append(s)

    return softened


def _trail_off(s: str) -> str:
    """End a sentence with a soft "..." instead of its period. Questions and
    exclamations keep their punctuation."""
    if s.endswith(("...", "…", "?", "!")):
        return s
    return s.rstrip(".") + "..."


# Emoji and pictograph blocks only, so curly quotes (’) and ellipses (…) survive.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]+"
)


def _clean_for_speech(text: str) -> str:
    """
    Remove markdown and emoji that TTS would read aloud or stumble over.
    The model is asked for plain text, so this is a safety net.
    """
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)       # headings
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)    # bullets
    text = text.replace("**", "").replace("*", "").replace("`", "")  # bold/italic/code
    text = re.sub(r"(?<!\w)__?(.+?)__?(?!\w)", r"\1", text)          # _italic_/__bold__
    text = re.sub(r"[ \t]{2,}", " ", text)                           # gaps left behind
    return text.strip()


def format_for_tts(text: str, tone: str | None = None) -> str:
    """
    Take the plain reply text and reshape it a bit so TTS sounds more expressive:
      - shorter lines
      - gentle pauses with ellipses
      - extra line breaks for important / emotional sentences

    We try to keep meaning intact while giving TTS more structure to work with.
    If `tone` is not given, it is guessed from the text with detect_tone().
    """
    text = _clean_for_speech(text)
    if not text:
        return text

    tone = tone or detect_tone(text)
    sentences = _split_sentences(text)

    # First pass: gently soften any existing name at the start (sympathetic only)
    sentences = _soften_existing_name(sentences, tone)

    shaped_lines: list[str] = []

    if tone in (TONE_SYMPATHETIC, TONE_BUMMED):
        # One sentence per line, with extra spacing and gentle ellipses
        for i, s in enumerate(sentences):
            lower_s = s.lower()
            if any(word in lower_s for word in ["sorry", "hard", "tough", "understand", "alone", "worried"]):
                s = _trail_off(s)
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
                last = _trail_off(last)
            elif tone in (TONE_HAPPY, TONE_EXCITED):
                # Excited/happy tends to land on a clear exclamation
                # (but leave questions as questions)
                if not last.endswith(("!", "?")):
                    last = last.rstrip(".…") + "!"
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

