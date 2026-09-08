/**
 * The animation engine, mirrored from `backend/app/domain/animation.py`.
 *
 * Preview and render must agree, so this file is a deliberate line-by-line port
 * rather than an approximation. `animation.test.ts` pins the numbers against the
 * values the Python implementation produces.
 */
import type { AnimationType } from "@/lib/api/types";

export const MIN_ZOOM = 1.0;
export const MAX_ZOOM = 2.5;

export interface Viewport {
  zoom: number;
  cx: number;
  cy: number;
}

export interface Motion {
  start: Viewport;
  end: Viewport;
  rotationStartDeg: number;
  rotationEndDeg: number;
  parallaxPx: number;
}

export function clamp(value: number, low: number, high: number): number {
  return value < low ? low : value > high ? high : value;
}

/** Clamp so the visible window never leaves the source image. */
export function normaliseViewport(viewport: Viewport): Viewport {
  const zoom = clamp(viewport.zoom, MIN_ZOOM, MAX_ZOOM);
  const half = 0.5 / zoom;
  return {
    zoom,
    cx: clamp(viewport.cx, half, 1 - half),
    cy: clamp(viewport.cy, half, 1 - half),
  };
}

export function viewportAt(motion: Motion, progress: number): Viewport {
  const t = clamp(progress, 0, 1);
  const { start: s, end: e } = motion;
  return {
    zoom: s.zoom + (e.zoom - s.zoom) * t,
    cx: s.cx + (e.cx - s.cx) * t,
    cy: s.cy + (e.cy - s.cy) * t,
  };
}

export function rotationAt(motion: Motion, progress: number): number {
  const t = clamp(progress, 0, 1);
  return motion.rotationStartDeg + (motion.rotationEndDeg - motion.rotationStartDeg) * t;
}

export function needsRotation(motion: Motion): boolean {
  return Math.abs(motion.rotationStartDeg) > 1e-3 || Math.abs(motion.rotationEndDeg) > 1e-3;
}

export function buildMotion(
  animation: AnimationType,
  options: { intensity?: number; focus?: [number, number] } = {},
): Motion {
  const i = clamp(options.intensity ?? 1, 0.3, 2);
  const fx = clamp(options.focus?.[0] ?? 0.5, 0, 1);
  const fy = clamp(options.focus?.[1] ?? 0.5, 0, 1);

  const zSmall = 1 + 0.08 * i;
  const zMed = 1 + 0.18 * i;
  const zLarge = 1 + 0.34 * i;
  const panTravel = 0.16 * i;

  const vp = (zoom: number, cx?: number, cy?: number): Viewport =>
    normaliseViewport({ zoom, cx: cx ?? fx, cy: cy ?? fy });

  const motion = (
    start: Viewport,
    end: Viewport,
    rotationStartDeg = 0,
    rotationEndDeg = 0,
    parallaxPx = 0,
  ): Motion => ({ start, end, rotationStartDeg, rotationEndDeg, parallaxPx });

  switch (animation) {
    case "none":
      return motion(vp(1, 0.5, 0.5), vp(1, 0.5, 0.5));
    case "zoom_in":
      return motion(vp(1, 0.5, 0.5), vp(zMed));
    case "zoom_out":
      return motion(vp(zMed), vp(1, 0.5, 0.5));
    case "slow_zoom":
      return motion(vp(1, 0.5, 0.5), vp(zSmall));
    case "dynamic_zoom":
      return motion(vp(zLarge), vp(1 + 0.02 * i, 0.5, 0.5));
    case "pan_left":
    case "pan_right":
    case "pan_up":
    case "pan_down": {
      const zoom = zMed;
      const half = 0.5 / zoom;
      const span = Math.min(panTravel, Math.max(0, 0.5 - half));
      const dx = animation === "pan_left" ? -1 : animation === "pan_right" ? 1 : 0;
      const dy = animation === "pan_up" ? -1 : animation === "pan_down" ? 1 : 0;
      return motion(
        normaliseViewport({ zoom, cx: 0.5 - dx * span, cy: 0.5 - dy * span }),
        normaliseViewport({ zoom, cx: 0.5 + dx * span, cy: 0.5 + dy * span }),
      );
    }
    case "ken_burns":
      return motion(
        normaliseViewport({ zoom: 1 + 0.04 * i, cx: 0.5, cy: 0.5 }),
        normaliseViewport({ zoom: zMed + 0.06 * i, cx: fx, cy: fy }),
      );
    case "rotate_slight": {
      const amount = 1.2 * i;
      return motion(vp(zSmall + 0.06, 0.5, 0.5), vp(zSmall + 0.1, 0.5, 0.5), -amount, amount);
    }
    case "parallax": {
      const zoom = zMed;
      const half = 0.5 / zoom;
      const span = Math.min(0.1 * i, Math.max(0, 0.5 - half));
      return motion(
        normaliseViewport({ zoom, cx: 0.5 - span, cy: 0.5 }),
        normaliseViewport({ zoom, cx: 0.5 + span, cy: 0.5 }),
        0,
        0,
        42 * i,
      );
    }
    default:
      return motion(vp(1, 0.5, 0.5), vp(zSmall));
  }
}

/**
 * The source rectangle to sample for a given viewport.
 *
 * The backend cover-crops the image to the canvas aspect before animating, so the
 * preview does the same: first the cover crop, then the viewport window inside it.
 * This is what makes the browser frame match the rendered frame.
 */
export function sourceRect(
  viewport: Viewport,
  imageWidth: number,
  imageHeight: number,
  frameWidth: number,
  frameHeight: number,
  focus: [number, number] = [0.5, 0.5],
): { sx: number; sy: number; sw: number; sh: number } {
  const scale = Math.max(frameWidth / imageWidth, frameHeight / imageHeight);
  const coverW = frameWidth / scale;
  const coverH = frameHeight / scale;

  let coverX = focus[0] * imageWidth - coverW / 2;
  let coverY = focus[1] * imageHeight - coverH / 2;
  coverX = clamp(coverX, 0, Math.max(0, imageWidth - coverW));
  coverY = clamp(coverY, 0, Math.max(0, imageHeight - coverH));

  const windowW = coverW / viewport.zoom;
  const windowH = coverH / viewport.zoom;
  const sx = coverX + clamp(viewport.cx * coverW - windowW / 2, 0, coverW - windowW);
  const sy = coverY + clamp(viewport.cy * coverH - windowH / 2, 0, coverH - windowH);

  return { sx, sy, sw: windowW, sh: windowH };
}
