"use client";

import { Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import type { Capabilities, Language } from "@/lib/api/types";

/**
 * The project's language (requirement: `Project.language`).
 *
 * It is not a cosmetic setting: it decides the instruction handed to the planner,
 * the default voice, and whether subtitles are laid out right to left.
 *
 * The fallback labels below exist so the control still works when
 * `GET /capabilities` has not answered — the language matters to the planner and to
 * subtitle direction even in a deployment with no text-to-speech at all.
 */
const FALLBACK: Array<{ code: Language; label: string }> = [
  { code: "en", label: "English" },
  { code: "fr", label: "French" },
  { code: "ar", label: "Arabic" },
  { code: "tn", label: "Tunisian Arabic (derja)" },
];

export function LanguageSelect({
  value,
  capabilities,
  disabled,
  onChange,
}: {
  value: Language;
  capabilities?: Capabilities;
  disabled?: boolean;
  onChange: (language: Language) => void;
}) {
  const support = capabilities?.voiceover.languages ?? [];
  const options = (support.length ? support : FALLBACK).map((entry) => ({
    value: entry.code,
    label: entry.label,
  }));

  const selected = support.find((entry) => entry.code === value);
  const voiceConfigured = capabilities?.voiceover.available ?? false;

  return (
    <div className="space-y-2">
      <Select
        label="Language"
        hint="Sets how the script is written, which voice reads it, and the subtitle direction."
        value={value}
        options={options}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value as Language)}
      />

      {/* Only speak about voices once a provider exists — otherwise the honest
          message is the voice-over panel's ("no TTS provider configured"), not a
          per-language complaint about a provider that isn't there. */}
      {voiceConfigured && selected && !selected.supported ? (
        <Notice tone="warning">
          {selected.note || `No ${selected.label} voice is available from this provider.`} The script
          and the subtitles still use {selected.label}.
        </Notice>
      ) : null}

      {voiceConfigured && selected?.supported && !selected.exact ? (
        <Notice tone="warning">{selected.note}</Notice>
      ) : null}
    </div>
  );
}
