import { describe, expect, it } from "vitest";
import { buildTimeline, effectiveTransition, formatTime, frameAt, totalDuration } from "./timeline";
import type { Scene, TransitionType } from "@/lib/api/types";

function scene(
  id: string,
  order: number,
  duration: number,
  transition: TransitionType = "none",
  transitionDuration = 0,
): Scene {
  return {
    id,
    order,
    media_id: null,
    duration,
    animation: "none",
    animation_intensity: 1,
    focus_x: 0.5,
    focus_y: 0.5,
    transition,
    transition_duration: transitionDuration,
    texts: [],
    background_color: "#000000",
    note: "",
    ai_motion: null,
    start_time: 0,
    media: null,
  };
}

describe("timeline arithmetic", () => {
  it("stacks scenes end to end when there are no transitions", () => {
    const timeline = buildTimeline([scene("a", 0, 3), scene("b", 1, 2)]);
    expect(timeline.map((item) => item.start)).toEqual([0, 3]);
    expect(totalDuration([scene("a", 0, 3), scene("b", 1, 2)])).toBe(5);
  });

  it("overlaps scenes by the transition length", () => {
    const scenes = [scene("a", 0, 3), scene("b", 1, 2, "fade", 0.5)];
    const timeline = buildTimeline(scenes);
    expect(timeline[1].start).toBeCloseTo(2.5, 6);
    expect(totalDuration(scenes)).toBeCloseTo(4.5, 6);
  });

  it("clamps a transition to 90% of the shorter neighbour", () => {
    const scenes = [scene("a", 0, 1), scene("b", 1, 3, "fade", 2.5)];
    expect(effectiveTransition(scenes, 1)).toBeCloseTo(0.9, 6);
  });

  it("ignores a transition on the first scene", () => {
    const scenes = [scene("a", 0, 2, "zoom", 0.8), scene("b", 1, 2)];
    expect(effectiveTransition(scenes, 0)).toBe(0);
    expect(buildTimeline(scenes)[0].start).toBe(0);
  });

  it("sorts by order, not by array position", () => {
    const timeline = buildTimeline([scene("b", 1, 2), scene("a", 0, 3)]);
    expect(timeline.map((item) => item.scene.id)).toEqual(["a", "b"]);
  });
});

describe("frameAt", () => {
  const scenes = [scene("a", 0, 3), scene("b", 1, 2, "fade", 0.6), scene("c", 2, 2)];
  const timeline = buildTimeline(scenes);

  it("returns null with no scenes", () => {
    expect(frameAt([], 0)).toBeNull();
  });

  it("resolves the single active scene outside a transition", () => {
    const state = frameAt(timeline, 1)!;
    expect(state.current.scene.id).toBe("a");
    expect(state.previous).toBeUndefined();
  });

  it("reports both scenes during the overlap", () => {
    const start = timeline[1].start;
    const state = frameAt(timeline, start + 0.3)!;
    expect(state.current.scene.id).toBe("b");
    expect(state.previous?.scene.id).toBe("a");
    expect(state.transition).toBe("fade");
    expect(state.progress).toBeGreaterThan(0);
    expect(state.progress).toBeLessThan(1);
  });

  it("runs the transition progress from 0 to 1 across the overlap", () => {
    const item = timeline[1];
    expect(frameAt(timeline, item.start)!.progress).toBeCloseTo(0, 5);
    expect(frameAt(timeline, item.start + item.transitionIn - 0.001)!.progress).toBeGreaterThan(0.99);
  });

  it("holds the last scene past the end", () => {
    const state = frameAt(timeline, 999)!;
    expect(state.current.scene.id).toBe("c");
  });
});

describe("formatTime", () => {
  it.each([
    [0, "0:00.0"],
    [1.25, "0:01.2"],
    [61.5, "1:01.5"],
    [-4, "0:00.0"],
  ])("formats %ss as %s", (input, expected) => {
    expect(formatTime(input)).toBe(expected);
  });
});
