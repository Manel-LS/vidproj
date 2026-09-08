"""Subtitles: turning spoken words into readable, timed lines.

Pure domain — no I/O, no framework, and deliberately no import from the TTS layer.
The provider's `WordTiming` is an infrastructure type; this module works on
`SpokenWord`, which callers build from whatever they stored. Keeping the two apart
is what lets the same grouping run over Edge timings today and another provider's
tomorrow without either shape leaking into the renderer.

Two ideas carry the module:

**Grouping.** A subtitle is not one word at a time. Reading a line that is replaced
every 300 ms is exhausting, and a phrase split across two cards loses its sense. So
words are gathered into cards that break on the things a reader actually notices —
a pause in the speech, a sentence ending, or a line getting too long to scan.

**Highlighting.** Within a card, each word keeps its own window, so the renderer can
mark the one being spoken. That is the whole point of the format: the eye is led
rather than asked to re-read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.enums import FontFamily, StrEnum, TextBackground


class SubtitleStyle(StrEnum):
    """How subtitles look. `NONE` means the video carries none."""

    NONE = "none"
    CLEAN = "clean"
    TIKTOK = "tiktok"
    BOLD = "bold"
    CINEMATIC = "cinematic"
    MINIMAL = "minimal"


#: A pause longer than this ends the card, whatever else is going on: it is where
#: the speaker themselves put a boundary.
PAUSE_BREAK_SECONDS = 0.45
#: Cards are capped by both, because either alone gives bad lines: characters only
#: lets six tiny words through, words only lets six long ones overflow the frame.
DEFAULT_MAX_CHARS = 34
DEFAULT_MAX_WORDS = 6
#: A card left on screen longer than this after its last word has gone stale.
MAX_TRAILING_SECONDS = 0.6
#: Below this a card flashes rather than reads.
MIN_CUE_SECONDS = 0.5

_SENTENCE_END = re.compile(r"[.!?…؟。]$")


@dataclass(frozen=True)
class SpokenWord:
    """One word and when it is said, in seconds from the start of the narration."""

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return round(self.start + self.duration, 4)

    @classmethod
    def from_mapping(cls, raw: dict) -> "SpokenWord":
        return cls(
            text=str(raw.get("text", "")),
            start=max(0.0, float(raw.get("start", 0.0))),
            duration=max(0.0, float(raw.get("duration", 0.0))),
        )


@dataclass(frozen=True)
class SubtitleWord:
    """A word inside a cue, with its window relative to the whole narration."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class SubtitleCue:
    """One card: the words shown together, and how long the card is up."""

    words: list[SubtitleWord] = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def duration(self) -> float:
        return round(max(0.0, self.end - self.start), 4)

    def active_index(self, at: float) -> int:
        """Which word is being spoken at `at`, or -1 before the first one.

        The last word stays marked until the card leaves, rather than the highlight
        vanishing on the final syllable and leaving a card that looks broken.
        """
        index = -1
        for position, word in enumerate(self.words):
            if at >= word.start:
                index = position
        return index


def parse_words(raw: list[dict] | None) -> list[SpokenWord]:
    """Read stored timings, dropping anything that is not usable.

    Empty text and zero-length entries are discarded rather than rendered: a
    provider that emits a boundary for punctuation would otherwise put a blank
    highlight in the middle of a line.
    """
    words: list[SpokenWord] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        word = SpokenWord.from_mapping(entry)
        if word.text.strip():
            words.append(word)
    return sorted(words, key=lambda w: w.start)


def build_cues(
    words: list[SpokenWord],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_words: int = DEFAULT_MAX_WORDS,
    pause_break: float = PAUSE_BREAK_SECONDS,
    limit: float | None = None,
) -> list[SubtitleCue]:
    """Group timed words into subtitle cards.

    `limit` is the length of the video: a narration longer than the picture would
    otherwise keep emitting cards over a video that has ended.
    """
    if not words:
        return []

    cues: list[SubtitleCue] = []
    current: list[SubtitleWord] = []

    def flush(next_start: float | None) -> None:
        if not current:
            return
        start = current[0].start
        last_end = current[-1].end
        # The card lingers until the next one is due, but not indefinitely — a long
        # silence should clear the screen, not freeze the last line on it.
        if next_start is None:
            end = last_end + MAX_TRAILING_SECONDS
        else:
            end = min(next_start, last_end + MAX_TRAILING_SECONDS)
        end = max(end, start + MIN_CUE_SECONDS)
        cues.append(SubtitleCue(words=list(current), start=round(start, 4), end=round(end, 4)))
        current.clear()

    for index, word in enumerate(words):
        if limit is not None and word.start >= limit:
            break

        previous = words[index - 1] if index else None
        gap = word.start - previous.end if previous else 0.0
        pending = " ".join(w.text for w in current)

        if current and (
            gap >= pause_break
            or len(current) >= max_words
            or len(f"{pending} {word.text}") > max_chars
            or _SENTENCE_END.search(current[-1].text or "")
        ):
            flush(word.start)

        current.append(
            SubtitleWord(text=word.text, start=round(word.start, 4), end=round(word.end, 4))
        )

    flush(None)

    if limit is not None:
        clipped: list[SubtitleCue] = []
        for cue in cues:
            if cue.start >= limit:
                break
            clipped.append(
                cue if cue.end <= limit else SubtitleCue(words=cue.words, start=cue.start, end=round(limit, 4))
            )
        cues = clipped

    return cues


def cues_from_sentences(script: str, total_duration: float) -> list[SubtitleCue]:
    """The fallback when no word timings exist.

    Words are spread evenly across the narration. That is an estimate and it is
    only good enough for whole lines — which is exactly why the result carries one
    `SubtitleWord` per card rather than per word: there is no honest way to
    highlight a word whose timing was invented.
    """
    sentences = [part.strip() for part in re.split(r"(?<=[.!?…؟])\s+|\n+", script or "") if part.strip()]
    if not sentences or total_duration <= 0:
        return []

    weights = [max(1, len(sentence)) for sentence in sentences]
    total_weight = sum(weights)
    cues: list[SubtitleCue] = []
    cursor = 0.0
    for sentence, weight in zip(sentences, weights):
        span = total_duration * (weight / total_weight)
        start, end = round(cursor, 4), round(min(cursor + span, total_duration), 4)
        cues.append(
            SubtitleCue(words=[SubtitleWord(text=sentence, start=start, end=end)], start=start, end=end)
        )
        cursor += span
    return cues


# -------------------------------------------------------------- appearance ----


@dataclass(frozen=True)
class SubtitlePreset:
    """How a subtitle card is typeset and how the spoken word is marked.

    Sizes are in pixels on the 1080-wide canvas and scaled with the frame, so a
    preset reads the same in 9:16 and 1:1.
    """

    key: SubtitleStyle
    name: str
    description: str
    font_family: FontFamily = FontFamily.SANS_BOLD
    font_size: int = 58
    #: Fraction of the frame height, measured to the middle of the block.
    position_y: float = 0.78
    max_width_pct: float = 0.86
    color: str = "#FFFFFF"
    #: Colour of the word being spoken. Equal to `color` means the highlight is
    #: carried by something other than hue — scale, or a filled pill.
    active_color: str = "#FFD166"
    #: Multiplier applied to the active word. 1.0 leaves the line still.
    active_scale: float = 1.0
    #: Opacity of the words that are not being spoken. Below 1.0 the highlight is
    #: carried by the rest of the line receding rather than by the word changing —
    #: which is the whole idea of the quieter presets.
    inactive_opacity: float = 1.0
    #: Filled shape behind the active word, rather than behind the whole line.
    active_background: str = ""
    background: TextBackground = TextBackground.NONE
    background_color: str = "#000000"
    background_opacity: float = 0.0
    uppercase: bool = False
    letter_spacing: float = 0.0
    line_height: float = 1.18
    shadow: bool = True
    #: A dark rim around every glyph. It is what keeps white text legible over a
    #: bright sky without darkening the whole frame with a box.
    outline_px: int = 0
    outline_color: str = "#000000"
    max_chars: int = DEFAULT_MAX_CHARS
    max_words: int = DEFAULT_MAX_WORDS


SUBTITLE_PRESETS: dict[SubtitleStyle, SubtitlePreset] = {
    SubtitleStyle.CLEAN: SubtitlePreset(
        key=SubtitleStyle.CLEAN,
        name="Clean",
        description="White, unobtrusive, one clear line. The spoken word warms to amber.",
        font_size=54,
        position_y=0.80,
        outline_px=4,
        shadow=True,
    ),
    SubtitleStyle.TIKTOK: SubtitlePreset(
        key=SubtitleStyle.TIKTOK,
        name="TikTok",
        description="Big, centred, uppercase, with the spoken word in a filled pill.",
        font_size=72,
        position_y=0.62,
        color="#FFFFFF",
        active_color="#101014",
        active_background="#39E08B",
        active_scale=1.06,
        uppercase=True,
        letter_spacing=0.5,
        outline_px=6,
        max_chars=26,
        max_words=4,
    ),
    SubtitleStyle.BOLD: SubtitlePreset(
        key=SubtitleStyle.BOLD,
        name="Bold",
        description="Heavy type with a thick rim; the spoken word jumps in yellow.",
        font_size=80,
        position_y=0.70,
        active_color="#FFE14D",
        active_scale=1.12,
        uppercase=True,
        outline_px=9,
        max_chars=24,
        max_words=4,
    ),
    SubtitleStyle.CINEMATIC: SubtitlePreset(
        key=SubtitleStyle.CINEMATIC,
        name="Cinematic",
        description="Low, restrained, letterbox-style. No colour change — the word simply brightens.",
        font_family=FontFamily.SANS,
        font_size=46,
        position_y=0.88,
        color="#D8D8D8",
        active_color="#FFFFFF",
        background=TextBackground.GRADIENT,
        background_color="#000000",
        background_opacity=0.35,
        letter_spacing=0.8,
        outline_px=0,
        max_chars=42,
        max_words=8,
    ),
    SubtitleStyle.MINIMAL: SubtitlePreset(
        key=SubtitleStyle.MINIMAL,
        name="Minimal",
        description="Small and quiet at the bottom. The spoken word is the only one at full opacity.",
        font_family=FontFamily.SANS,
        font_size=40,
        position_y=0.90,
        color="#FFFFFF",
        active_color="#FFFFFF",
        inactive_opacity=0.45,
        outline_px=3,
        max_chars=38,
        max_words=7,
    ),
}


def get_subtitle_preset(style: SubtitleStyle | str) -> SubtitlePreset | None:
    """The preset for a style, or None when subtitles are switched off."""
    try:
        key = SubtitleStyle(style)
    except ValueError:
        return None
    return SUBTITLE_PRESETS.get(key)
