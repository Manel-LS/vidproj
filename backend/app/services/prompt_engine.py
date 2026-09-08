"""Every prompt the pipeline sends, built in one place.

Four kinds of prompt leave this application — story, image, video, voice — and
before this module they were built in three different files, each with its own
idea of what a good prompt contains. That inconsistency is not cosmetic: a scene
whose image prompt omits "photorealistic, 9:16" comes back square and stylised,
and nothing downstream can recover from it.

Two properties are load-bearing:

**Deterministic.** The same inputs produce the same string, byte for byte. It is
what makes regenerating a scene reproduce the same shot instead of a new one, and
it is what lets these functions be tested without a network.

**Ordered.** Subject first, then framing, then environment, then light, then
camera, then the technical clauses. Image models weight early tokens more
heavily, so the subject leading is not a stylistic preference.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Language, VideoFormat, VideoStyle
from app.domain.language import get_profile
from app.domain.styles import get_style_preset

#: Appended to every image prompt. Kept in one constant because a scene missing
#: them comes back square, painterly, or both.
IMAGE_TECHNICAL = ("photorealistic", "cinematic", "shallow depth of field")

#: Appended to every video prompt. "no morphing" earns its place: without it,
#: image-to-video models routinely melt a face between keyframes.
VIDEO_TECHNICAL = ("photorealistic", "natural motion", "no morphing", "no text overlay")


@dataclass(frozen=True)
class ShotBrief:
    """One scene, described in the terms an image model understands."""

    framing: str = ""          # "Close-up", "Medium shot"
    action: str = ""           # "facing camera with a worried frown"
    environment: str = ""      # "a Tunisian wedding hall"
    lighting: str = ""         # "warm golden window light"
    camera: str = ""           # "slow push-in"
    background: str = ""       # "clapping guests softly blurred behind"


@dataclass(frozen=True)
class MotionBrief:
    """One scene's movement, in the terms an image-to-video model understands."""

    face: str = ""             # "eyebrows draw together, then a slow blink"
    mouth: str = ""            # "lips move as he speaks"
    head: str = ""             # "small tilt to the left"
    hands: str = ""            # "one hand rises to touch his cap"
    body: str = ""             # "shoulders shift once"
    background: str = ""       # "guests clap and sway slowly"
    camera: str = ""           # "locked, very slow push-in"


def _join(parts: list[str]) -> str:
    """Comma-join, dropping empties and stray punctuation.

    A prompt containing ", ," or trailing commas measurably degrades output, and
    empty fields are the normal case rather than the exception.
    """
    cleaned = [part.strip().rstrip(",.") for part in parts if part and part.strip()]
    return ", ".join(cleaned)


def aspect_clause(format: VideoFormat | str) -> str:
    value = format.value if isinstance(format, VideoFormat) else str(format)
    return {"9:16": "9:16 vertical", "4:5": "4:5 vertical", "1:1": "1:1 square"}.get(
        value, "16:9 horizontal"
    )


# ------------------------------------------------------------------- story ----


def story_prompt(
    *,
    idea: str,
    language: Language | str,
    duration_seconds: float,
    style: VideoStyle,
    character_description: str = "",
    scene_count: int = 6,
) -> str:
    """The brief for the script writer.

    Duration is expressed in **spoken words**, not seconds: a model told "30
    seconds" has no way to count them and reliably overshoots by half again.
    Roughly 2.3 words per second is a natural narration pace.
    """
    preset = get_style_preset(style)
    profile = get_profile(language)
    words = max(12, int(duration_seconds * 2.3))

    lines = [
        f"Write a {duration_seconds:.0f}-second script for a vertical short video.",
        "",
        f"Idea: {idea.strip() or '(none given — infer something simple and human)'}",
        f"Style: {preset.name} — {preset.description}",
        f"Language: {profile.prompt_instruction}",
        "",
        "Structure:",
        "  1. A hook in the first 1–2 seconds. It must work with the sound off.",
        "  2. The body, in short spoken sentences.",
        "  3. A turn — the funny or moving beat the video exists for.",
        "  4. An ending that lands. No trailing summary.",
        "",
        f"Length: about {words} spoken words in total, across {scene_count} scenes.",
        "Each scene's line must be short enough to read as a subtitle: two lines at most.",
    ]
    if character_description:
        lines += [
            "",
            f"It is spoken by: {character_description}",
            "Write in that character's voice, not as a narrator describing them.",
        ]
    return "\n".join(lines)


# ------------------------------------------------------------------- image ----


def image_prompt(
    *,
    shot: ShotBrief,
    character_description: str = "",
    format: VideoFormat | str = VideoFormat.PORTRAIT_9_16,
    extra: str = "",
) -> str:
    """The prompt for one scene's still image.

    The character clause leads, verbatim, and is prefixed with "the same" — that
    phrase is what tells the model the subject is a returning one rather than a
    fresh invention. Everything after it describes the shot, never the subject.
    """
    parts: list[str] = []
    # Framing and subject are one phrase — "Close-up, of the same toddler" reads
    # as two fragments, so they are joined before the comma-separated list starts.
    if shot.framing and character_description:
        parts.append(f"{shot.framing} of the same {character_description}")
    elif character_description:
        parts.append(f"The same {character_description}")
    elif shot.framing:
        parts.append(shot.framing)
    if shot.action:
        parts.append(shot.action)
    if shot.environment:
        parts.append(f"in {shot.environment}" if not shot.environment.startswith("in ") else shot.environment)
    if shot.background:
        parts.append(shot.background)
    if shot.lighting:
        parts.append(shot.lighting)
    if shot.camera:
        parts.append(shot.camera)
    if extra:
        parts.append(extra)
    parts.extend(IMAGE_TECHNICAL)
    parts.append(aspect_clause(format))
    return _join(parts)


# ------------------------------------------------------------------- video ----


def video_prompt(
    *,
    motion: MotionBrief,
    duration_seconds: float,
    format: VideoFormat | str = VideoFormat.PORTRAIT_9_16,
    speaking: bool = True,
) -> str:
    """The prompt for animating one still.

    Movement is enumerated body part by body part. A single "make him move
    naturally" produces either a frozen frame or a face that drifts; naming the
    face, mouth, head, hands, body and background is what gets each of them moving.
    """
    movement = _join(
        [
            motion.face,
            motion.mouth or ("lips move naturally as they speak" if speaking else ""),
            motion.head,
            motion.hands,
            motion.body,
        ]
    )
    parts = [movement or "subtle natural movement"]
    if motion.background:
        parts.append(f"in the background, {motion.background}")
    parts.append(motion.camera or "camera locked, very slow push-in")
    parts.append(f"{duration_seconds:.0f} seconds")
    parts.extend(VIDEO_TECHNICAL)
    parts.append(aspect_clause(format))
    return _join(parts)


# ------------------------------------------------------------------- voice ----


def voice_prompt(*, language: Language | str, character_description: str = "", style: VideoStyle | None = None) -> str:
    """Delivery direction, for providers that accept a style instruction.

    Providers that do not accept one ignore this; it is never sent as text to be
    read aloud. Keeping it here means the direction exists in one place the day a
    provider can use it.
    """
    profile = get_profile(language)
    parts = [f"Speak in {profile.label}"]
    if character_description:
        parts.append(f"as {character_description}")
    if style is not None:
        parts.append(get_style_preset(style).prompt_hint or get_style_preset(style).description)
    parts.append("natural conversational pace, clear diction, no announcer tone")
    return _join(parts)
