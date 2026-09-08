"use client";

import { Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import type {
  Capabilities,
  ProjectDetail,
  SubtitleStyleKey,
  SubtitleStyleOption,
} from "@/lib/api/types";

/**
 * Burned-in subtitles.
 *
 * The distinction the control has to make honestly: word-by-word highlighting needs
 * per-word timings from the text-to-speech provider. Without them subtitles still
 * work — whole lines, timed across the narration — but no word is lit, and saying
 * so up front is better than the user discovering it in the export.
 */
const FALLBACK: SubtitleStyleOption[] = [
  { key: "none", name: "No subtitles", description: "The video carries no burned-in text." },
  { key: "clean", name: "Clean", description: "White, unobtrusive, one clear line." },
  { key: "tiktok", name: "TikTok", description: "Big, uppercase, spoken word in a filled pill." },
  { key: "bold", name: "Bold", description: "Heavy type with a thick rim." },
  { key: "cinematic", name: "Cinematic", description: "Low and restrained, letterbox style." },
  { key: "minimal", name: "Minimal", description: "Small and quiet at the bottom." },
];

export function SubtitleStyleSelect({
  project,
  options,
  capabilities,
  disabled,
  onChange,
}: {
  project: ProjectDetail;
  options?: SubtitleStyleOption[];
  capabilities?: Capabilities;
  disabled?: boolean;
  onChange: (style: SubtitleStyleKey) => void;
}) {
  const entries = options?.length ? options : FALLBACK;
  const current = entries.find((entry) => entry.key === project.subtitle_style);
  const on = project.subtitle_style !== "none";

  const voice = project.voice_over;
  const hasNarration = Boolean(voice?.enabled && voice.media);
  const hasWordTimings = Boolean(voice?.has_word_timings);
  const providerCanTime = capabilities?.voiceover.supports_word_timings ?? false;

  return (
    <div className="space-y-2">
      <Select
        label="Subtitles"
        hint="Burned into the video, so they show wherever it is posted."
        value={project.subtitle_style}
        disabled={disabled}
        options={entries.map((entry) => ({ value: entry.key, label: entry.name }))}
        onChange={(event) => onChange(event.target.value as SubtitleStyleKey)}
      />

      {on && current ? <p className="text-2xs text-faint">{current.description}</p> : null}

      {on && !hasNarration ? (
        <Notice tone="info">
          Subtitles are drawn from the voice-over. Generate one and they will appear.
        </Notice>
      ) : null}

      {on && hasNarration && !hasWordTimings ? (
        <Notice tone="warning">
          {providerCanTime
            ? "This narration was generated before word timings were recorded. Regenerate the voice-over to get word-by-word highlighting."
            : "This voice provider does not report word timings, so subtitles show whole lines without highlighting a word."}
        </Notice>
      ) : null}
    </div>
  );
}
