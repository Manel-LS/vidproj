/**
 * Parity tests for subtitle grouping.
 *
 * `subtitle-parity.json` is generated from the Python engine
 * (`backend/app/domain/subtitles.py`). If the two implementations drift, the user
 * edits against one picture and exports another — cards breaking in different
 * places, or a different word lit.
 *
 * Regenerate with:
 *   python backend/scripts/export_subtitle_parity.py
 */
import { describe, expect, it } from "vitest";
import parity from "./__fixtures__/subtitle-parity.json";
import {
  activeIndex,
  buildCues,
  cueAt,
  cuesFromSentences,
  getSubtitlePreset,
  parseWords,
} from "./subtitles";
import type { SubtitleStyleKey, WordTiming } from "@/lib/api/types";

const EPSILON = 1e-4;

const SAMPLES: Record<string, WordTiming[]> = {
  simple: [
    { text: "Bonjour", start: 0.1, duration: 0.62 },
    { text: "a", start: 0.8, duration: 0.1 },
    { text: "tous", start: 0.95, duration: 0.33 },
  ],
  pause: [
    { text: "Bonjour", start: 0.1, duration: 0.4 },
    { text: "tous", start: 0.55, duration: 0.3 },
    { text: "Aujourdhui", start: 1.6, duration: 0.5 },
    { text: "on", start: 2.15, duration: 0.12 },
    { text: "commence", start: 2.3, duration: 0.45 },
  ],
  punctuation: [
    { text: "Voila.", start: 0.0, duration: 0.4 },
    { text: "Ensuite", start: 0.5, duration: 0.4 },
    { text: "on", start: 0.95, duration: 0.12 },
    { text: "continue", start: 1.1, duration: 0.45 },
  ],
  long_words: [
    { text: "incomprehensible", start: 0.0, duration: 0.6 },
    { text: "anticonstitutionnel", start: 0.7, duration: 0.7 },
    { text: "court", start: 1.5, duration: 0.3 },
  ],
  many_short: Array.from({ length: 11 }, (_, i) => ({
    text: `m${i}`,
    start: Math.round(i * 0.3 * 10000) / 10000,
    duration: 0.25,
  })),
  arabic: [
    { text: "أهلا", start: 0.1, duration: 0.38 },
    { text: "بكم", start: 0.56, duration: 0.34 },
    { text: "معانا", start: 1.28, duration: 0.3 },
    { text: "اليوم", start: 1.65, duration: 0.4 },
  ],
};

const LIMITS: Record<string, number | undefined> = {
  simple: undefined,
  pause: undefined,
  punctuation: 1.2,
  long_words: undefined,
  many_short: 2.0,
  arabic: undefined,
};

type FixtureCue = { start: number; end: number; words: { text: string; start: number; end: number }[] };
const fixture = parity as {
  cues: Record<string, FixtureCue[]>;
  active: Record<string, number>;
  sentences: Record<string, FixtureCue[]>;
};

describe("subtitle parity with the Python engine", () => {
  const entries = Object.entries(fixture.cues);

  it("covers every style against every awkward sample", () => {
    expect(entries.length).toBe(30);
  });

  it.each(entries)("groups %s the same way", (key, expected) => {
    const [style, sample] = key.split("|");
    const preset = getSubtitlePreset(style as SubtitleStyleKey);
    expect(preset).not.toBeNull();

    const actual = buildCues(parseWords(SAMPLES[sample]), {
      maxChars: preset!.maxChars,
      maxWords: preset!.maxWords,
      limit: LIMITS[sample],
    });

    expect(actual).toHaveLength(expected.length);
    actual.forEach((cue, index) => {
      const want = expected[index];
      expect(cue.start).toBeCloseTo(want.start, 4);
      expect(cue.end).toBeCloseTo(want.end, 4);
      expect(cue.words.map((w) => w.text)).toEqual(want.words.map((w) => w.text));
      cue.words.forEach((word, position) => {
        expect(Math.abs(word.start - want.words[position].start)).toBeLessThan(EPSILON);
        expect(Math.abs(word.end - want.words[position].end)).toBeLessThan(EPSILON);
      });
    });
  });

  it("lights the same word at the same instant", () => {
    const cue = buildCues(parseWords(SAMPLES.simple))[0];
    Object.entries(fixture.active).forEach(([at, expected]) => {
      expect(activeIndex(cue, Number(at))).toBe(expected);
    });
  });

  it("splits an untimed script into the same lines", () => {
    const even = cuesFromSentences("Une. Deux. Trois.", 9.0);
    expect(even.map((c) => c.words[0].text)).toEqual(
      fixture.sentences.even.map((c) => c.words[0].text),
    );
    even.forEach((cue, index) => {
      expect(cue.start).toBeCloseTo(fixture.sentences.even[index].start, 3);
      expect(cue.end).toBeCloseTo(fixture.sentences.even[index].end, 3);
    });

    const weighted = cuesFromSentences("Court. Une phrase nettement plus longue.", 6.0);
    weighted.forEach((cue, index) => {
      expect(cue.end).toBeCloseTo(fixture.sentences.weighted[index].end, 3);
    });
  });
});

describe("subtitle helpers", () => {
  it("has no preset for 'none', which is how subtitles are switched off", () => {
    expect(getSubtitlePreset("none")).toBeNull();
    expect(getSubtitlePreset(undefined)).toBeNull();
  });

  it("drops entries that would render as a blank highlight", () => {
    expect(
      parseWords([
        { text: "un", start: 0.1, duration: 0.2 },
        { text: "  ", start: 0.4, duration: 0.2 },
      ]).map((w) => w.text),
    ).toEqual(["un"]);
  });

  it("finds the card on screen, and nothing between cards", () => {
    const cues = buildCues(parseWords(SAMPLES.pause));
    expect(cueAt(cues, 0.5)).not.toBeNull();
    expect(cueAt(cues, 99)).toBeNull();
  });
});
