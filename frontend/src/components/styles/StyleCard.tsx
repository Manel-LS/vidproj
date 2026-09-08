"use client";

import { Check } from "lucide-react";
import type { StylePreset } from "@/lib/api/types";
import { cn, humanise } from "@/lib/utils";

/**
 * A style card.
 *
 * The preview thumbnail is generated from the preset itself — its gradient, its
 * typography and its default text position — so it genuinely previews the look
 * rather than showing a stock image that might not match.
 */
export function StyleCard({
  preset,
  selected,
  onSelect,
}: {
  preset: StylePreset;
  selected: boolean;
  onSelect: (key: StylePreset["key"]) => void;
}) {
  const [from, to] = preset.gradient;
  const typo = preset.typography;

  const positionClass = {
    top: "items-start pt-4",
    upper_third: "items-start pt-8",
    center: "items-center",
    lower_third: "items-end pb-8",
    bottom: "items-end pb-4",
  }[preset.text_position];

  return (
    <button
      type="button"
      onClick={() => onSelect(preset.key)}
      aria-pressed={selected}
      className={cn(
        "group relative overflow-hidden rounded-card border bg-surface text-left transition-all",
        selected
          ? "border-accent ring-2 ring-accent/30"
          : "border-line hover:border-accent/45 hover:shadow-card",
      )}
    >
      <div
        className="relative flex aspect-[4/5] w-full justify-center overflow-hidden px-3"
        style={{ background: `linear-gradient(150deg, ${from} 0%, ${to} 100%)` }}
      >
        {/* A faint frame so the thumbnail reads as a phone screen. */}
        <span className="absolute inset-2 rounded-lg border border-white/15" aria-hidden />

        <span className={cn("relative flex w-full flex-col justify-center", positionClass)}>
          <span
            className={cn(
              "mx-auto max-w-[92%] px-2 py-1 text-center leading-tight",
              typo.background !== "none" && "rounded-md",
            )}
            style={{
              color: typo.color,
              fontFamily:
                typo.family === "serif"
                  ? "Georgia, serif"
                  : typo.family === "mono"
                    ? "ui-monospace, monospace"
                    : typo.family === "condensed"
                      ? "'Arial Narrow', sans-serif"
                      : "inherit",
              fontWeight: typo.family === "sans" ? 500 : 800,
              letterSpacing: `${Math.min(typo.letter_spacing, 3) * 0.5}px`,
              textTransform: typo.uppercase ? "uppercase" : "none",
              fontSize: "13px",
              textShadow: typo.shadow ? "0 1px 6px rgba(0,0,0,0.5)" : "none",
              background:
                typo.background === "none"
                  ? "transparent"
                  : `${typo.background_color}${Math.round(typo.background_opacity * 255)
                      .toString(16)
                      .padStart(2, "0")}`,
            }}
          >
            {preset.tagline}
          </span>
          <span
            className="mx-auto mt-1.5 text-center text-[10px] font-medium"
            style={{ color: typo.accent_color }}
          >
            {preset.default_cta}
          </span>
        </span>

        {selected ? (
          <span className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-white text-black">
            <Check className="h-3.5 w-3.5" aria-hidden />
          </span>
        ) : null}
      </div>

      <div className="p-3">
        <p className="text-sm font-medium text-ink">{preset.name}</p>
        <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-muted">
          {preset.description}
        </p>
        <p className="mt-2 flex flex-wrap gap-1 text-2xs text-faint">
          <span className="rounded bg-elevated px-1.5 py-0.5">
            {preset.scene_seconds[0]}–{preset.scene_seconds[1]}s scenes
          </span>
          <span className="rounded bg-elevated px-1.5 py-0.5">
            {humanise(preset.animations[0] ?? "ken_burns")}
          </span>
        </p>
      </div>
    </button>
  );
}
