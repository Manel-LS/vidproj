/**
 * Parity tests.
 *
 * `animation-parity.json` is generated from the Python engine
 * (`backend/app/domain/animation.py`). If the two implementations ever drift, this
 * fails — which matters, because a preview that lies about the render is worse than
 * no preview at all.
 *
 * Regenerate with:
 *   python -c "..."  (see backend/scripts/export_animation_parity.py)
 */
import { describe, expect, it } from "vitest";
import parity from "./__fixtures__/animation-parity.json";
import {
  MAX_ZOOM,
  buildMotion,
  normaliseViewport,
  sourceRect,
  viewportAt,
} from "./animation";
import type { AnimationType } from "@/lib/api/types";

const EPSILON = 1e-5;

describe("animation parity with the Python renderer", () => {
  const entries = Object.entries(parity as Record<string, number[]>);

  it("covers every animation at several intensities", () => {
    expect(entries.length).toBeGreaterThanOrEqual(36);
  });

  it.each(entries)("matches the backend for %s", (key, expected) => {
    const [animation, intensity, focus] = key.split("|");
    const [fx, fy] = focus.split(",").map(Number);
    const motion = buildMotion(animation as AnimationType, {
      intensity: Number(intensity),
      focus: [fx, fy],
    });

    const actual = [
      motion.start.zoom,
      motion.start.cx,
      motion.start.cy,
      motion.end.zoom,
      motion.end.cx,
      motion.end.cy,
      motion.rotationStartDeg,
      motion.rotationEndDeg,
      motion.parallaxPx,
    ];

    actual.forEach((value, index) => {
      expect(value).toBeCloseTo(expected[index], 5);
    });
  });
});

describe("viewport clamping", () => {
  it("never lets the window leave the image", () => {
    for (const zoom of [1, 1.2, 1.8, 2.5, 9]) {
      for (const cx of [-1, 0, 0.5, 1, 2]) {
        const viewport = normaliseViewport({ zoom, cx, cy: cx });
        const half = 0.5 / viewport.zoom;
        expect(viewport.zoom).toBeLessThanOrEqual(MAX_ZOOM + EPSILON);
        expect(viewport.cx).toBeGreaterThanOrEqual(half - EPSILON);
        expect(viewport.cx).toBeLessThanOrEqual(1 - half + EPSILON);
      }
    }
  });

  it("interpolates linearly between start and end", () => {
    const motion = buildMotion("zoom_in", { intensity: 1 });
    const midpoint = viewportAt(motion, 0.5);
    expect(midpoint.zoom).toBeCloseTo((motion.start.zoom + motion.end.zoom) / 2, 6);
    expect(viewportAt(motion, 0).zoom).toBeCloseTo(motion.start.zoom, 6);
    expect(viewportAt(motion, 1).zoom).toBeCloseTo(motion.end.zoom, 6);
  });

  it("clamps progress outside 0..1", () => {
    const motion = buildMotion("pan_right");
    expect(viewportAt(motion, -5)).toEqual(viewportAt(motion, 0));
    expect(viewportAt(motion, 5)).toEqual(viewportAt(motion, 1));
  });
});

describe("sourceRect", () => {
  it("cover-crops a landscape image into a vertical frame", () => {
    const rect = sourceRect({ zoom: 1, cx: 0.5, cy: 0.5 }, 1920, 1080, 1080, 1920);
    // The frame is much taller than the source, so the full height is used and the
    // width is cropped down to the 9:16 slice.
    expect(rect.sh).toBeCloseTo(1080, 3);
    expect(rect.sw).toBeCloseTo((1080 / 1920) * 1080, 3);
    expect(rect.sx).toBeGreaterThan(0);
  });

  it("stays inside the source at any zoom", () => {
    for (const zoom of [1, 1.5, 2.4]) {
      const rect = sourceRect({ zoom, cx: 0.95, cy: 0.05 }, 1200, 1600, 1080, 1920, [0.9, 0.1]);
      expect(rect.sx).toBeGreaterThanOrEqual(-EPSILON);
      expect(rect.sy).toBeGreaterThanOrEqual(-EPSILON);
      expect(rect.sx + rect.sw).toBeLessThanOrEqual(1200 + EPSILON);
      expect(rect.sy + rect.sh).toBeLessThanOrEqual(1600 + EPSILON);
    }
  });

  it("samples a smaller window as the zoom increases", () => {
    const wide = sourceRect({ zoom: 1, cx: 0.5, cy: 0.5 }, 1200, 1600, 1080, 1920);
    const tight = sourceRect({ zoom: 2, cx: 0.5, cy: 0.5 }, 1200, 1600, 1080, 1920);
    expect(tight.sw).toBeLessThan(wide.sw);
    expect(tight.sh).toBeLessThan(wide.sh);
  });
});
