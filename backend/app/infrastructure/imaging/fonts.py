"""Font resolution for text rasterisation.

Text is drawn with Pillow, so we need real font files. We look for a family/weight
match across the platform font directories, cache what we find, and always fall back
to something that exists rather than crashing a render. `RENDER_FONT_PATH` overrides
everything, which is how a deployment ships its own brand typeface.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import FontFamily

logger = get_logger(__name__)

FONT_DIRS: list[Path] = [
    Path(__file__).resolve().parents[3] / "assets" / "fonts",
    Path("C:/Windows/Fonts"),
    Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
]

#: Candidate filenames per (family, bold), most preferred first.
_CANDIDATES: dict[tuple[FontFamily, bool], tuple[str, ...]] = {
    (FontFamily.SANS_BOLD, True): (
        "Inter-Bold.ttf", "Montserrat-Bold.ttf", "Poppins-Bold.ttf",
        "segoeuib.ttf", "arialbd.ttf", "Roboto-Bold.ttf",
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf",
        "Helvetica.ttc", "ariblk.ttf",
    ),
    (FontFamily.SANS_BOLD, False): (
        "Inter-SemiBold.ttf", "segoeuisb.ttf", "seguisb.ttf", "arialbd.ttf",
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
    ),
    (FontFamily.SANS, False): (
        "Inter-Regular.ttf", "segoeui.ttf", "arial.ttf", "Roboto-Regular.ttf",
        "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf",
        "Helvetica.ttc",
    ),
    (FontFamily.SANS, True): (
        "Inter-Bold.ttf", "segoeuib.ttf", "arialbd.ttf",
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
    ),
    (FontFamily.SERIF, False): (
        "PlayfairDisplay-Regular.ttf", "georgia.ttf", "times.ttf",
        "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "NotoSerif-Regular.ttf",
        "Times New Roman.ttf",
    ),
    (FontFamily.SERIF, True): (
        "PlayfairDisplay-Bold.ttf", "georgiab.ttf", "timesbd.ttf",
        "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf",
    ),
    (FontFamily.CONDENSED, False): (
        "Oswald-Regular.ttf", "BebasNeue-Regular.ttf", "ARIALN.TTF", "arialn.ttf",
        "DejaVuSansCondensed.ttf", "LiberationSansNarrow-Regular.ttf", "impact.ttf",
    ),
    (FontFamily.CONDENSED, True): (
        "Oswald-Bold.ttf", "BebasNeue-Regular.ttf", "ARIALNB.TTF", "arialnb.ttf",
        "impact.ttf", "DejaVuSansCondensed-Bold.ttf",
    ),
    (FontFamily.MONO, False): (
        "JetBrainsMono-Regular.ttf", "consola.ttf", "DejaVuSansMono.ttf",
        "LiberationMono-Regular.ttf", "Menlo.ttc", "cour.ttf",
    ),
    (FontFamily.MONO, True): (
        "JetBrainsMono-Bold.ttf", "consolab.ttf", "DejaVuSansMono-Bold.ttf",
        "LiberationMono-Bold.ttf", "courbd.ttf",
    ),
}

#: Arabic needs its own candidates: several of the families above (Georgia,
#: Arial Narrow, Consolas) carry no Arabic glyphs at all and would render every
#: letter as an empty box. Condensed and mono have no Arabic equivalent on a
#: typical system, so they fall back to a naskh or a sans that does cover it.
_ARABIC_CANDIDATES: dict[tuple[FontFamily, bool], tuple[str, ...]] = {
    (FontFamily.SANS_BOLD, True): (
        "NotoSansArabic-Bold.ttf", "NotoNaskhArabic-Bold.ttf", "DUBAI-BOLD.TTF",
        "segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf",
    ),
    (FontFamily.SANS_BOLD, False): (
        "NotoSansArabic-SemiBold.ttf", "DUBAI-MEDIUM.TTF", "segoeuib.ttf", "arialbd.ttf",
    ),
    (FontFamily.SANS, False): (
        "NotoSansArabic-Regular.ttf", "DUBAI-REGULAR.TTF", "segoeui.ttf",
        "arial.ttf", "tahoma.ttf",
    ),
    (FontFamily.SANS, True): (
        "NotoSansArabic-Bold.ttf", "DUBAI-BOLD.TTF", "segoeuib.ttf", "arialbd.ttf",
    ),
    # Naskh is the Arabic answer to a serif: calligraphic, used for scripture and
    # literary text. Times New Roman carries a usable Arabic face; Georgia does not.
    (FontFamily.SERIF, False): (
        "NotoNaskhArabic-Regular.ttf", "Amiri-Regular.ttf", "trado.ttf",
        "times.ttf", "arial.ttf",
    ),
    (FontFamily.SERIF, True): (
        "NotoNaskhArabic-Bold.ttf", "Amiri-Bold.ttf", "tradbdo.ttf",
        "timesbd.ttf", "arialbd.ttf",
    ),
    (FontFamily.CONDENSED, False): ("DUBAI-REGULAR.TTF", "segoeui.ttf", "arial.ttf", "tahoma.ttf"),
    (FontFamily.CONDENSED, True): ("DUBAI-BOLD.TTF", "segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf"),
    (FontFamily.MONO, False): ("NotoSansArabic-Regular.ttf", "segoeui.ttf", "arial.ttf"),
    (FontFamily.MONO, True): ("NotoSansArabic-Bold.ttf", "segoeuib.ttf", "arialbd.ttf"),
}

#: Last resort for Arabic, before giving up and using the universal list.
_ARABIC_FALLBACKS = (
    "segoeui.ttf", "arial.ttf", "tahoma.ttf", "times.ttf",
    "NotoSansArabic-Regular.ttf", "DejaVuSans.ttf",
)

#: Last resort, in order, regardless of the requested family.
_UNIVERSAL_FALLBACKS = (
    "DejaVuSans.ttf", "arial.ttf", "segoeui.ttf", "LiberationSans-Regular.ttf",
    "NotoSans-Regular.ttf", "Verdana.ttf", "verdana.ttf",
)


@lru_cache(maxsize=1)
def _font_index() -> dict[str, Path]:
    """Lowercased filename -> path, for every font we can see."""
    index: dict[str, Path] = {}
    for directory in FONT_DIRS:
        if not directory.is_dir():
            continue
        try:
            for path in directory.rglob("*"):
                if path.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    index.setdefault(path.name.lower(), path)
        except (PermissionError, OSError):  # pragma: no cover - platform dependent
            continue
    return index


class FontUnavailableError(RuntimeError):
    pass


@lru_cache(maxsize=64)
def resolve_font_path(family: FontFamily, bold: bool, arabic: bool = False) -> Path:
    """Find a font file for this family and weight, covering the right script."""
    if settings.render_font_path:
        override = Path(settings.render_font_path)
        if override.is_file():
            return override
        logger.warning("RENDER_FONT_PATH=%s does not exist; falling back.", override)

    index = _font_index()
    if arabic:
        candidates = (
            _ARABIC_CANDIDATES.get((family, bold), ())
            + _ARABIC_CANDIDATES.get((family, not bold), ())
            + _ARABIC_FALLBACKS
        )
        for name in candidates:
            found = index.get(name.lower())
            if found:
                return found
        # Nothing Arabic-capable was found; the universal list below is better than
        # nothing, though it will very likely render empty boxes.
        logger.warning("No Arabic-capable font found for %s; text may not render.", family.value)

    candidates = _CANDIDATES.get((family, bold), ()) + _CANDIDATES.get((family, not bold), ())
    for name in candidates + _UNIVERSAL_FALLBACKS:
        found = index.get(name.lower())
        if found:
            return found

    if index:  # any font is better than no render
        return next(iter(index.values()))
    raise FontUnavailableError(
        "No usable font was found on this system. Set RENDER_FONT_PATH to a .ttf file "
        "or install a font package (e.g. fonts-dejavu-core)."
    )


@lru_cache(maxsize=256)
def load_font(
    family: FontFamily, weight: int, size: int, arabic: bool = False
) -> ImageFont.FreeTypeFont:
    path = resolve_font_path(family, weight >= 600, arabic)
    try:
        return ImageFont.truetype(str(path), size=max(8, int(size)))
    except OSError:  # pragma: no cover - corrupt/unsupported font file
        logger.warning("Could not load font %s; using Pillow's default.", path)
        return ImageFont.load_default(size=max(8, int(size)))


def font_report() -> dict[str, str]:
    """Diagnostics surfaced by /capabilities so misconfiguration is visible."""
    report: dict[str, str] = {}
    for family in FontFamily:
        for bold in (False, True):
            label = f"{family.value}:{'bold' if bold else 'regular'}"
            try:
                report[label] = str(resolve_font_path(family, bold))
            except FontUnavailableError:
                report[label] = "unavailable"
    report["platform"] = sys.platform
    return report
