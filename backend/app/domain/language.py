"""What each supported language means to the rest of the pipeline.

One table, three consumers: the planner is told which language to write in, the
voice-over picks a matching voice, and the subtitle renderer needs to know the
script runs right to left.

Tunisian Arabic is listed separately from Modern Standard Arabic on purpose. They
are not interchangeable for this product — a script written in MSA read by an MSA
voice sounds like a news bulletin, which is the opposite of the register these
videos want. The voice tags differ too (`ar-TN` against `ar-SA`, `ar-EG`), so the
distinction has to survive all the way to voice selection.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import Language


@dataclass(frozen=True)
class LanguageProfile:
    code: Language
    #: Shown in the UI.
    label: str
    #: The instruction handed to the LLM. Written as a directive because a bare
    #: language name produces a translation of an English draft rather than a
    #: script thought in that language.
    prompt_instruction: str
    #: Right-to-left script: the subtitle renderer shapes and aligns accordingly.
    rtl: bool = False
    #: BCP-47 prefixes matched against a provider's voice ids, most specific first.
    voice_prefixes: tuple[str, ...] = ()
    #: Fallbacks when no voice matches the preferred prefixes. Empty means the
    #: language genuinely cannot be voiced by that provider — say so, do not
    #: quietly substitute a different accent.
    fallback_prefixes: tuple[str, ...] = field(default=())


_PROFILES: dict[Language, LanguageProfile] = {
    Language.TUNISIAN: LanguageProfile(
        code=Language.TUNISIAN,
        label="Tunisian Arabic (derja)",
        prompt_instruction=(
            "Write in Tunisian Arabic (derja) as it is actually spoken — everyday spoken "
            "vocabulary, short sentences, Arabic script. Do not write Modern Standard "
            "Arabic, and do not transliterate into Latin letters."
        ),
        rtl=True,
        voice_prefixes=("ar-TN",),
        # Another Maghrebi accent is closer than a Gulf one, but it is still not
        # Tunisian; the capability report has to admit the substitution.
        fallback_prefixes=("ar-DZ", "ar-MA", "ar-EG", "ar"),
    ),
    Language.ARABIC: LanguageProfile(
        code=Language.ARABIC,
        label="Arabic",
        prompt_instruction=(
            "Write in Modern Standard Arabic, in Arabic script. Keep sentences short "
            "enough to read as a subtitle."
        ),
        rtl=True,
        voice_prefixes=("ar-SA", "ar-EG", "ar"),
    ),
    Language.FRENCH: LanguageProfile(
        code=Language.FRENCH,
        label="French",
        prompt_instruction="Write in French, in a natural spoken register.",
        voice_prefixes=("fr-FR", "fr"),
    ),
    Language.ENGLISH: LanguageProfile(
        code=Language.ENGLISH,
        label="English",
        prompt_instruction="Write in English, in a natural spoken register.",
        voice_prefixes=("en-US", "en-GB", "en"),
    ),
}


def get_profile(language: Language | str) -> LanguageProfile:
    try:
        code = Language(language)
    except ValueError:
        code = Language.ENGLISH
    return _PROFILES[code]


def all_profiles() -> list[LanguageProfile]:
    return list(_PROFILES.values())


def is_rtl(language: Language | str) -> bool:
    return get_profile(language).rtl


def match_voice(voices, language: Language | str) -> tuple[object | None, bool]:
    """Pick the best voice for a language.

    Returns `(voice, exact)`. `exact` is False when only a fallback accent was
    found — the caller is expected to surface that rather than pass it off as a
    match, because "Tunisian" delivered in a Gulf accent is a defect the user
    hears immediately.
    """
    profile = get_profile(language)

    for prefix in profile.voice_prefixes:
        for voice in voices:
            if str(getattr(voice, "id", "")).lower().startswith(prefix.lower()):
                return voice, True

    for prefix in profile.fallback_prefixes:
        for voice in voices:
            if str(getattr(voice, "id", "")).lower().startswith(prefix.lower()):
                return voice, False

    return None, False


_ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def is_arabic_script(text: str) -> bool:
    """True when the text is mostly written in Arabic letters.

    "Mostly", not "contains": a French sentence quoting one Arabic word is still
    French, and an Arabic sentence carrying a Latin brand name is still Arabic.
    """
    letters = [char for char in (text or "") if char.isalpha()]
    if not letters:
        return False
    arabic = sum(
        1 for char in letters if any(low <= ord(char) <= high for low, high in _ARABIC_RANGES)
    )
    return arabic * 2 > len(letters)


def scripts_match(text: str, language: Language | str) -> bool:
    """Whether `text` is written in the script the language is read in.

    This is not pedantry about spelling. A Latin brand dropped into an Arabic line
    is pronounced letter by letter by an Arabic voice, and because the subtitle
    timings come from that same synthesis, the highlighting drifts with it. So the
    planner uses this to decide whether to weave the subject into the copy, and
    the caller can warn about it rather than let it surface as a bad recording.
    """
    text = (text or "").strip()
    if not text:
        return True
    return is_arabic_script(text) == get_profile(language).rtl


def language_support(voices) -> list[dict]:
    """Which languages the configured voice provider can actually speak.

    The point is to be honest per language: a provider with no `ar-TN` voice must
    not be reported as supporting derja.
    """
    report = []
    for profile in all_profiles():
        voice, exact = match_voice(voices, profile.code)
        report.append(
            {
                "code": profile.code.value,
                "label": profile.label,
                "rtl": profile.rtl,
                "supported": voice is not None,
                "exact": exact,
                "voice_id": getattr(voice, "id", None) if voice else None,
                "note": ""
                if exact
                else (
                    f"No {profile.label} voice from this provider"
                    + (
                        f"; the closest available accent is '{getattr(voice, 'id', '')}'."
                        if voice is not None
                        else "."
                    )
                ),
            }
        )
    return report
