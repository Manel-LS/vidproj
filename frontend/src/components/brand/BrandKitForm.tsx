"use client";

import { useRef, useState } from "react";
import { ImagePlus, Palette, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select, Slider } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import type { BrandKit, BrandKitDraft, LogoPosition } from "@/lib/api/types";

const POSITIONS: Array<{ value: LogoPosition; label: string }> = [
  { value: "top_left", label: "Top left" },
  { value: "top_right", label: "Top right" },
  { value: "bottom_left", label: "Bottom left" },
  { value: "bottom_right", label: "Bottom right" },
];

const EMPTY: BrandKitDraft = {
  name: "",
  brand_name: "",
  slogan: "",
  primary_color: "#FFFFFF",
  accent_color: "#FFD166",
  background_color: "#101014",
  logo_position: "top_right",
  logo_scale: 0.16,
  logo_opacity: 0.9,
};

/**
 * A brand's constants.
 *
 * The preview on the right is not decoration: colours picked as hex codes in a
 * form are impossible to judge, and the whole point of a kit is that the same
 * three colours appear on every video. Seeing them on a frame-shaped card is the
 * difference between choosing them and guessing them.
 */
export function BrandKitForm({
  kit,
  saving,
  uploading,
  onSave,
  onUploadLogo,
  onCancel,
}: {
  kit: BrandKit | null;
  saving?: boolean;
  uploading?: boolean;
  onSave: (draft: BrandKitDraft) => void;
  onUploadLogo?: (file: File) => void;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<BrandKitDraft>(
    kit ? { ...(kit as unknown as BrandKitDraft) } : { ...EMPTY },
  );
  const fileInput = useRef<HTMLInputElement>(null);

  function set<K extends keyof BrandKitDraft>(key: K, value: BrandKitDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  const named = Boolean(draft.name?.trim());
  const corner = draft.logo_position ?? "top_right";

  return (
    <form
      className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,220px)]"
      onSubmit={(event) => {
        event.preventDefault();
        if (named) onSave(draft);
      }}
    >
      <div className="space-y-4">
        <Input
          label="Kit name"
          value={draft.name ?? ""}
          onChange={(event) => set("name", event.target.value)}
          placeholder="Nova — main brand"
          maxLength={120}
          required
          hint="Only you see this; it is how you pick the kit."
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Brand name"
            value={draft.brand_name ?? ""}
            onChange={(event) => set("brand_name", event.target.value)}
            placeholder="Nova Stationery"
            maxLength={120}
          />
          <Input
            label="Slogan"
            value={draft.slogan ?? ""}
            onChange={(event) => set("slogan", event.target.value)}
            placeholder="La rentrée, en mieux"
            maxLength={200}
          />
        </div>

        <fieldset className="grid grid-cols-3 gap-3">
          <legend className="field-label mb-1">Colours</legend>
          <ColourField
            label="Text"
            value={draft.primary_color ?? "#FFFFFF"}
            onChange={(value) => set("primary_color", value)}
          />
          <ColourField
            label="Accent"
            value={draft.accent_color ?? "#FFD166"}
            onChange={(value) => set("accent_color", value)}
          />
          <ColourField
            label="Card"
            value={draft.background_color ?? "#101014"}
            onChange={(value) => set("background_color", value)}
          />
        </fieldset>

        <div className="rounded-xl border border-line p-3">
          <div className="flex items-start gap-3">
            <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-elevated">
              {kit?.logo_url ? (
                <img src={kit.logo_url} alt="" className="max-h-full max-w-full object-contain" />
              ) : (
                <Palette className="h-6 w-6 text-faint" aria-hidden />
              )}
            </span>
            <div className="min-w-0 flex-1">
              {kit ? (
                <>
                  <input
                    ref={fileInput}
                    type="file"
                    accept="image/png,image/webp,image/jpeg"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) onUploadLogo?.(file);
                      event.target.value = "";
                    }}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    loading={uploading}
                    icon={<ImagePlus className="h-3.5 w-3.5" />}
                    onClick={() => fileInput.current?.click()}
                  >
                    {kit.logo_url ? "Replace logo" : "Add logo"}
                  </Button>
                  <p className="mt-1.5 text-2xs text-faint">
                    A PNG with a transparent background sits best on a photograph.
                  </p>
                </>
              ) : (
                <p className="text-xs text-faint">Save the kit first, then add a logo.</p>
              )}
            </div>
          </div>

          {kit?.logo_url ? (
            <div className="mt-3 space-y-3">
              <Select
                label="Corner"
                value={corner}
                options={POSITIONS}
                onChange={(event) => set("logo_position", event.target.value as LogoPosition)}
              />
              <Slider
                label="Size"
                value={draft.logo_scale ?? 0.16}
                min={0.04}
                max={0.35}
                step={0.01}
                onChange={(value) => set("logo_scale", Number(value.toFixed(2)))}
              />
              <Slider
                label="Opacity"
                value={draft.logo_opacity ?? 0.9}
                min={0.1}
                max={1}
                step={0.05}
                onChange={(value) => set("logo_opacity", Number(value.toFixed(2)))}
              />
            </div>
          ) : null}
        </div>

        <div className="flex justify-end gap-2">
          {onCancel ? (
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          ) : null}
          <Button type="submit" loading={saving} disabled={!named}>
            {kit ? "Save changes" : "Create brand kit"}
          </Button>
        </div>
      </div>

      <BrandPreview draft={draft} logoUrl={kit?.logo_url ?? null} />
    </form>
  );
}

/** A hex field with the native picker beside it, because typing hex is not choosing. */
function ColourField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <span className="mt-1 flex items-center gap-1.5">
        <input
          type="color"
          aria-label={`${label} colour`}
          value={value}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-line bg-transparent p-0.5"
        />
        <input
          type="text"
          aria-label={`${label} hex`}
          value={value}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="input-base min-w-0 flex-1 font-mono text-xs"
          maxLength={7}
        />
      </span>
    </label>
  );
}

/** A 9:16 card showing the three colours and the logo where they will actually land. */
function BrandPreview({ draft, logoUrl }: { draft: BrandKitDraft; logoUrl: string | null }) {
  const corner = draft.logo_position ?? "top_right";
  const place = {
    top_left: "left-2 top-2",
    top_right: "right-2 top-2",
    bottom_left: "bottom-2 left-2",
    bottom_right: "bottom-2 right-2",
  }[corner];

  return (
    <div>
      <span className="field-label">Preview</span>
      <div
        className="relative mt-1 aspect-[9/16] w-full overflow-hidden rounded-xl border border-line"
        style={{ backgroundColor: draft.background_color ?? "#101014" }}
      >
        {logoUrl ? (
          <img
            src={logoUrl}
            alt=""
            className={`absolute ${place} object-contain`}
            style={{
              width: `${(draft.logo_scale ?? 0.16) * 100}%`,
              opacity: draft.logo_opacity ?? 0.9,
            }}
          />
        ) : null}

        <div className="absolute inset-x-3 bottom-8 space-y-1.5 text-center">
          <p
            className="text-sm font-semibold leading-tight"
            style={{ color: draft.primary_color ?? "#FFFFFF" }}
          >
            {draft.brand_name?.trim() || "Your brand"}
          </p>
          <p className="text-xs" style={{ color: draft.accent_color ?? "#FFD166" }}>
            {draft.slogan?.trim() || "Your slogan"}
          </p>
        </div>
      </div>
      <Notice tone="info" className="mt-2">
        The logo is burned into every video made with this kit.
      </Notice>
    </div>
  );
}

export function BrandKitCard({
  kit,
  selected,
  onSelect,
  onDelete,
}: {
  kit: BrandKit;
  selected?: boolean;
  onSelect: () => void;
  onDelete?: () => void;
}) {
  return (
    <article
      className={
        selected
          ? "flex items-center gap-3 rounded-card border border-accent bg-accent/5 p-3"
          : "flex items-center gap-3 rounded-card border border-line bg-surface p-3 transition-colors hover:border-accent/40"
      }
    >
      <button type="button" onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <span
          className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-lg"
          style={{ backgroundColor: kit.background_color }}
        >
          {kit.logo_url ? (
            <img src={kit.logo_url} alt="" className="max-h-full max-w-full object-contain" />
          ) : (
            <span className="h-4 w-4 rounded-full" style={{ backgroundColor: kit.accent_color }} />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">{kit.name}</span>
          <span className="block truncate text-xs text-muted">
            {kit.brand_name || kit.slogan || "No brand name yet"}
          </span>
        </span>
        <span className="flex shrink-0 gap-1" aria-hidden>
          {[kit.primary_color, kit.accent_color, kit.background_color].map((colour) => (
            <span
              key={colour}
              className="h-3.5 w-3.5 rounded-full border border-line"
              style={{ backgroundColor: colour }}
            />
          ))}
        </span>
      </button>
      {onDelete ? (
        <Button variant="ghost" size="icon" aria-label={`Delete ${kit.name}`} onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
        </Button>
      ) : null}
    </article>
  );
}
