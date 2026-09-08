/**
 * Timeline arithmetic, mirrored from `VideoPlan` in the backend domain.
 *
 * The preview scrubber, the timeline ruler and the render must all agree on where
 * each scene starts, so the maths lives in one place and is unit-tested.
 */
import type { Scene, TransitionType, VideoFormat } from "@/lib/api/types";

export const FORMAT_DIMENSIONS: Record<VideoFormat, [number, number]> = {
  "9:16": [1080, 1920],
  "1:1": [1080, 1080],
  "16:9": [1920, 1080],
  "4:5": [1080, 1350],
};

export interface TimelineScene {
  scene: Scene;
  index: number;
  start: number;
  end: number;
  /** Length of the cross-fade into this scene, already clamped. */
  transitionIn: number;
}

export function effectiveTransition(
  scenes: Pick<Scene, "duration" | "transition" | "transition_duration">[],
  index: number,
): number {
  if (index <= 0 || index >= scenes.length) return 0;
  const scene = scenes[index];
  if (scene.transition === "none") return 0;
  const previous = scenes[index - 1];
  return Math.max(
    0,
    Math.min(scene.transition_duration, previous.duration * 0.9, scene.duration * 0.9),
  );
}

export function buildTimeline(scenes: Scene[]): TimelineScene[] {
  const ordered = [...scenes].sort((a, b) => a.order - b.order);
  const result: TimelineScene[] = [];
  let cursor = 0;

  ordered.forEach((scene, index) => {
    const transitionIn = effectiveTransition(ordered, index);
    const start = index === 0 ? 0 : cursor - transitionIn;
    result.push({ scene, index, start, end: start + scene.duration, transitionIn });
    cursor = start + scene.duration;
  });

  return result;
}

export function totalDuration(scenes: Scene[]): number {
  const timeline = buildTimeline(scenes);
  if (!timeline.length) return 0;
  return Math.max(...timeline.map((item) => item.end));
}

/**
 * Which scene (or pair of scenes, mid-transition) is on screen at `time`.
 *
 * During a transition both the outgoing and incoming scene are live; `progress`
 * runs 0 → 1 across the overlap and drives whichever effect the transition uses.
 */
export interface FrameState {
  current: TimelineScene;
  previous?: TimelineScene;
  transition: TransitionType;
  progress: number;
}

export function frameAt(timeline: TimelineScene[], time: number): FrameState | null {
  if (!timeline.length) return null;

  // Later scenes win, so during an overlap we resolve to the incoming scene.
  let active = timeline[0];
  for (const item of timeline) {
    if (time >= item.start - 1e-6) active = item;
  }
  if (time > active.end) active = timeline[timeline.length - 1];

  const previous = active.index > 0 ? timeline[active.index - 1] : undefined;
  const overlap = active.transitionIn;
  const inTransition =
    previous !== undefined && overlap > 0 && time >= active.start && time < active.start + overlap;

  return {
    current: active,
    previous: inTransition ? previous : undefined,
    transition: inTransition ? active.scene.transition : "none",
    progress: inTransition ? (time - active.start) / overlap : 1,
  };
}

export function formatTime(seconds: number): string {
  const safe = Math.max(0, seconds);
  const whole = Math.floor(safe);
  const minutes = Math.floor(whole / 60);
  const remainder = whole % 60;
  const tenths = Math.floor((safe - whole) * 10);
  return `${minutes}:${String(remainder).padStart(2, "0")}.${tenths}`;
}
