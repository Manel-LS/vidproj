/**
 * The subtitle domain, mirrored from `backend/app/domain/subtitles.py`.
 *
 * The preview has to break words into the same cards, at the same instants, and
 * light the same word as the renderer — otherwise the user edits against one
 * picture and exports another. A parity test asserts the two agree; regenerate its
 * fixture with `python backend/scripts/export_subtitle_parity.py`.
 *
 * Only the timing and grouping live here. The look is described by presets, which
 * the server publishes, but the numbers below are duplicated deliberately: the
 * preview must be able to draw a band before `GET /options` has answered.
 */
import type { SubtitleStyleKey, WordTiming } from "@/lib/api/types";

export const PAUSE_BREAK_SECONDS = 0.45;
export const DEFAULT_MAX_CHARS = 34;
export const DEFAULT_MAX_WORDS = 6;
export const MAX_TRAILING_SECONDS = 0.6;
export const MIN_CUE_SECONDS = 0.5;

const SENTENCE_END = /[.!?…؟。]$/;

export interface SpokenWord {
  text: string;
  start: number;
  duration: number;
}

export interface SubtitleWord {
  text: string;
  start: number;
  end: number;
}

export interface SubtitleCue {
  words: SubtitleWord[];
  start: number;
  end: number;
}

export interface SubtitlePreset {
  key: SubtitleStyleKey;
  fontSize: number;
  positionY: number;
  maxWidthPct: number;
  color: string;
  activeColor: string;
  activeScale: number;
  activeBackground: string;
  inactiveOpacity: number;
  backgroundColor: string;
  backgroundOpacity: number;
  gradientBackground: boolean;
  uppercase: boolean;
  letterSpacing: number;
  lineHeight: number;
  outlinePx: number;
  outlineColor: string;
  maxChars: number;
  maxWords: number;
}

const BASE: Omit<SubtitlePreset, "key"> = {
  fontSize: 54,
  positionY: 0.8,
  maxWidthPct: 0.86,
  color: "#FFFFFF",
  activeColor: "#FFD166",
  activeScale: 1,
  activeBackground: "",
  inactiveOpacity: 1,
  backgroundColor: "#000000",
  backgroundOpacity: 0,
  gradientBackground: false,
  uppercase: false,
  letterSpacing: 0,
  lineHeight: 1.18,
  outlinePx: 0,
  outlineColor: "#000000",
  maxChars: DEFAULT_MAX_CHARS,
  maxWords: DEFAULT_MAX_WORDS,
};

export const SUBTITLE_PRESETS: Record<Exclude<SubtitleStyleKey, "none">, SubtitlePreset> = {
  clean: { ...BASE, key: "clean", fontSize: 54, positionY: 0.8, outlinePx: 4 },
  tiktok: {
    ...BASE,
    key: "tiktok",
    fontSize: 72,
    positionY: 0.62,
    activeColor: "#101014",
    activeBackground: "#39E08B",
    activeScale: 1.06,
    uppercase: true,
    letterSpacing: 0.5,
    outlinePx: 6,
    maxChars: 26,
    maxWords: 4,
  },
  bold: {
    ...BASE,
    key: "bold",
    fontSize: 80,
    positionY: 0.7,
    activeColor: "#FFE14D",
    activeScale: 1.12,
    uppercase: true,
    outlinePx: 9,
    maxChars: 24,
    maxWords: 4,
  },
  cinematic: {
    ...BASE,
    key: "cinematic",
    fontSize: 46,
    positionY: 0.88,
    color: "#D8D8D8",
    activeColor: "#FFFFFF",
    backgroundColor: "#000000",
    backgroundOpacity: 0.35,
    gradientBackground: true,
    letterSpacing: 0.8,
    maxChars: 42,
    maxWords: 8,
  },
  minimal: {
    ...BASE,
    key: "minimal",
    fontSize: 40,
    positionY: 0.9,
    activeColor: "#FFFFFF",
    inactiveOpacity: 0.45,
    outlinePx: 3,
    maxChars: 38,
    maxWords: 7,
  },
};

export function getSubtitlePreset(style: SubtitleStyleKey | undefined): SubtitlePreset | null {
  if (!style || style === "none") return null;
  return SUBTITLE_PRESETS[style] ?? null;
}

/** Drop entries that would render as a blank highlight, and order by time. */
export function parseWords(raw: WordTiming[] | undefined | null): SpokenWord[] {
  return (raw ?? [])
    .filter((entry) => entry && typeof entry.text === "string" && entry.text.trim().length > 0)
    .map((entry) => ({
      text: entry.text,
      start: Math.max(0, Number(entry.start) || 0),
      duration: Math.max(0, Number(entry.duration) || 0),
    }))
    .sort((a, b) => a.start - b.start);
}

const round = (value: number) => Math.round(value * 10000) / 10000;

export function buildCues(
  words: SpokenWord[],
  options: { maxChars?: number; maxWords?: number; pauseBreak?: number; limit?: number } = {},
): SubtitleCue[] {
  const maxChars = options.maxChars ?? DEFAULT_MAX_CHARS;
  const maxWords = options.maxWords ?? DEFAULT_MAX_WORDS;
  const pauseBreak = options.pauseBreak ?? PAUSE_BREAK_SECONDS;
  const limit = options.limit;
  if (!words.length) return [];

  const cues: SubtitleCue[] = [];
  let current: SubtitleWord[] = [];

  const flush = (nextStart: number | null) => {
    if (!current.length) return;
    const start = current[0].start;
    const lastEnd = current[current.length - 1].end;
    let end =
      nextStart === null
        ? lastEnd + MAX_TRAILING_SECONDS
        : Math.min(nextStart, lastEnd + MAX_TRAILING_SECONDS);
    end = Math.max(end, start + MIN_CUE_SECONDS);
    cues.push({ words: current, start: round(start), end: round(end) });
    current = [];
  };

  for (let index = 0; index < words.length; index += 1) {
    const word = words[index];
    if (limit !== undefined && word.start >= limit) break;

    const previous = index ? words[index - 1] : null;
    const gap = previous ? word.start - (previous.start + previous.duration) : 0;
    const pending = current.map((w) => w.text).join(" ");

    if (
      current.length &&
      (gap >= pauseBreak ||
        current.length >= maxWords ||
        `${pending} ${word.text}`.length > maxChars ||
        SENTENCE_END.test(current[current.length - 1].text))
    ) {
      flush(word.start);
    }

    current.push({
      text: word.text,
      start: round(word.start),
      end: round(word.start + word.duration),
    });
  }
  flush(null);

  if (limit === undefined) return cues;
  const clipped: SubtitleCue[] = [];
  for (const cue of cues) {
    if (cue.start >= limit) break;
    clipped.push(cue.end <= limit ? cue : { ...cue, end: round(limit) });
  }
  return clipped;
}

/**
 * Words spread across the narration when the provider reported no timings.
 * One span per card, never per word — a card whose words have invented clocks
 * must not pretend to highlight one.
 */
export function cuesFromSentences(script: string, totalDuration: number): SubtitleCue[] {
  const sentences = (script || "")
    .split(/(?<=[.!?…؟])\s+|\n+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!sentences.length || totalDuration <= 0) return [];

  const weights = sentences.map((sentence) => Math.max(1, sentence.length));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const cues: SubtitleCue[] = [];
  let cursor = 0;
  sentences.forEach((sentence, index) => {
    const span = totalDuration * (weights[index] / total);
    const start = round(cursor);
    const end = round(Math.min(cursor + span, totalDuration));
    cues.push({ words: [{ text: sentence, start, end }], start, end });
    cursor += span;
  });
  return cues;
}

/** The card on screen at `at`, or null. */
export function cueAt(cues: SubtitleCue[], at: number): SubtitleCue | null {
  return cues.find((cue) => at >= cue.start && at < cue.end) ?? null;
}

/**
 * Which word is being spoken, or -1 before the first one. The last word stays
 * marked until the card leaves, rather than the highlight vanishing on the final
 * syllable and leaving a card that looks broken.
 */
export function activeIndex(cue: SubtitleCue, at: number): number {
  let index = -1;
  cue.words.forEach((word, position) => {
    if (at >= word.start) index = position;
  });
  return index;
}
