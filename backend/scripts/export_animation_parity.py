"""Export animation reference values for the frontend parity test.

The browser preview reimplements `app.domain.animation` in TypeScript. This script
writes the Python engine's output to a fixture the frontend test asserts against, so
the two can never silently diverge.

    python scripts/export_animation_parity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.animation import build_motion  # noqa: E402
from app.domain.enums import AnimationType  # noqa: E402

TARGET = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "lib"
    / "video"
    / "__fixtures__"
    / "animation-parity.json"
)


def main() -> int:
    out: dict[str, list[float]] = {}
    for animation in AnimationType:
        for intensity in (0.5, 1.0, 1.6):
            for focus in ((0.5, 0.5), (0.3, 0.7)):
                motion = build_motion(animation, intensity=intensity, focus=focus)
                key = f"{animation.value}|{intensity}|{focus[0]},{focus[1]}"
                out[key] = [
                    round(motion.start.zoom, 6),
                    round(motion.start.cx, 6),
                    round(motion.start.cy, 6),
                    round(motion.end.zoom, 6),
                    round(motion.end.cx, 6),
                    round(motion.end.cy, 6),
                    round(motion.rotation_start_deg, 6),
                    round(motion.rotation_end_deg, 6),
                    round(motion.parallax_px, 6),
                ]

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} entries to {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
