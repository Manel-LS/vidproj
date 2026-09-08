"""Export subtitle grouping reference values for the frontend parity test.

The browser preview reimplements `app.domain.subtitles` in TypeScript. If the two
drift, the user edits against one picture and exports another — the cards break in
different places, or a different word is lit. This script writes the Python
engine's output to a fixture the frontend test asserts against.

    python scripts/export_subtitle_parity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.subtitles import (  # noqa: E402
    SubtitleStyle,
    build_cues,
    cues_from_sentences,
    get_subtitle_preset,
    parse_words,
)

TARGET = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "lib"
    / "video"
    / "__fixtures__"
    / "subtitle-parity.json"
)

#: Deliberately awkward: a sentence end, a long pause, a very long word, and a run
#: of short ones — the four things that decide where a card breaks.
SAMPLES: dict[str, list[dict]] = {
    "simple": [
        {"text": "Bonjour", "start": 0.10, "duration": 0.62},
        {"text": "a", "start": 0.80, "duration": 0.10},
        {"text": "tous", "start": 0.95, "duration": 0.33},
    ],
    "pause": [
        {"text": "Bonjour", "start": 0.10, "duration": 0.40},
        {"text": "tous", "start": 0.55, "duration": 0.30},
        {"text": "Aujourdhui", "start": 1.60, "duration": 0.50},
        {"text": "on", "start": 2.15, "duration": 0.12},
        {"text": "commence", "start": 2.30, "duration": 0.45},
    ],
    "punctuation": [
        {"text": "Voila.", "start": 0.00, "duration": 0.40},
        {"text": "Ensuite", "start": 0.50, "duration": 0.40},
        {"text": "on", "start": 0.95, "duration": 0.12},
        {"text": "continue", "start": 1.10, "duration": 0.45},
    ],
    "long_words": [
        {"text": "incomprehensible", "start": 0.00, "duration": 0.60},
        {"text": "anticonstitutionnel", "start": 0.70, "duration": 0.70},
        {"text": "court", "start": 1.50, "duration": 0.30},
    ],
    "many_short": [
        {"text": f"m{i}", "start": round(i * 0.30, 4), "duration": 0.25} for i in range(11)
    ],
    "arabic": [
        {"text": "أهلا", "start": 0.10, "duration": 0.38},
        {"text": "بكم", "start": 0.56, "duration": 0.34},
        {"text": "معانا", "start": 1.28, "duration": 0.30},
        {"text": "اليوم", "start": 1.65, "duration": 0.40},
    ],
}

LIMITS: dict[str, float | None] = {"simple": None, "pause": None, "punctuation": 1.2,
                                   "long_words": None, "many_short": 2.0, "arabic": None}


def _cue(cue) -> dict:
    return {
        "start": cue.start,
        "end": cue.end,
        "words": [{"text": w.text, "start": w.start, "end": w.end} for w in cue.words],
    }


def main() -> int:
    out: dict[str, dict] = {"cues": {}, "active": {}, "sentences": {}}

    for style in SubtitleStyle:
        preset = get_subtitle_preset(style)
        if preset is None:
            continue
        for name, raw in SAMPLES.items():
            words = parse_words(raw)
            cues = build_cues(
                words,
                max_chars=preset.max_chars,
                max_words=preset.max_words,
                limit=LIMITS[name],
            )
            out["cues"][f"{style.value}|{name}"] = [_cue(cue) for cue in cues]

    # The highlight, sampled across a card: the index must move at the same moments.
    words = parse_words(SAMPLES["simple"])
    cue = build_cues(words)[0]
    out["active"] = {
        f"{at:.2f}": cue.active_index(at)
        for at in (0.0, 0.05, 0.1, 0.5, 0.79, 0.8, 0.94, 0.95, 1.5, 3.0)
    }

    out["sentences"] = {
        "even": [_cue(c) for c in cues_from_sentences("Une. Deux. Trois.", 9.0)],
        "weighted": [
            _cue(c) for c in cues_from_sentences("Court. Une phrase nettement plus longue.", 6.0)
        ],
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET} ({len(out['cues'])} grouping cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
