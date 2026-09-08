"use client";

import { useMemo, useState } from "react";
import { Crosshair, Film, Plus, Sparkles, Trash2, Type } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select, Slider, Textarea, Toggle } from "@/components/ui/Field";
import { Badge, Notice } from "@/components/ui/Feedback";
import type {
  AnimationType,
  Capabilities,
  EditorOptions,
  MediaItem,
  Scene,
  TextAnimation,
  TextBackground,
  TextOverlay,
  TextPosition,
  TextRole,
  TransitionType,
} from "@/lib/api/types";
import { useEditorStore } from "@/lib/store/editor";
import { cn, humanise } from "@/lib/utils";

const DEFAULT_TEXT: Omit<TextOverlay, "id"> = {
  role: "subtitle",
  content: "Your text here",
  position: "lower_third",
  align: "center",
  animation: "fade",
  font_family: "sans_bold",
  font_size: 64,
  font_weight: 700,
  color: "#FFFFFF",
  letter_spacing: 0,
  line_height: 1.16,
  uppercase: false,
  opacity: 1,
  background: "none",
  background_color: "#000000",
  background_opacity: 0.45,
  shadow: true,
  max_width_pct: 0.84,
  offset_y_pct: 0,
  offset_x_pct: 0,
  start: 0.15,
  duration: null,
  animation_duration: 0.45,
};

/**
 * The right-hand properties panel.
 *
 * Edits are sent as a patch on blur/commit rather than on every keystroke, so the
 * server sees whole values and the preview does not thrash.
 */
export function SceneProperties({
  scene,
  sceneIndex,
  isFirst,
  images,
  options,
  capabilities,
  onChange,
  onGenerateAiMotion,
  saving,
}: {
  scene: Scene | null;
  sceneIndex: number;
  isFirst: boolean;
  images: MediaItem[];
  options: EditorOptions | undefined;
  capabilities: Capabilities | undefined;
  onChange: (changes: Record<string, unknown>) => void;
  onGenerateAiMotion: (prompt: string) => void;
  saving?: boolean;
}) {
  const { selectedTextId, selectText } = useEditorStore();
  const [aiPrompt, setAiPrompt] = useState("");

  const texts = useMemo(() => scene?.texts ?? [], [scene]);
  // Falls back to the first layer, so a scene whose selected layer was just deleted
  // still shows something without an effect having to repair the store first.
  const activeText = useMemo(
    () => texts.find((text) => text.id === selectedTextId) ?? texts[0] ?? null,
    [texts, selectedTextId],
  );

  if (!scene) {
    return (
      <div className="p-5 text-sm text-muted">
        Select a scene in the timeline to edit it.
      </div>
    );
  }

  function patchText(index: number, changes: Partial<TextOverlay>) {
    const next = texts.map((text, position) =>
      position === index ? { ...text, ...changes } : text,
    );
    onChange({ texts: next });
  }

  function addText() {
    if (texts.length >= 4) return;
    onChange({ texts: [...texts, { ...DEFAULT_TEXT, id: `text-${Date.now()}` }] });
  }

  function removeText(index: number) {
    onChange({ texts: texts.filter((_, position) => position !== index) });
  }

  const activeIndex = activeText ? texts.indexOf(activeText) : -1;
  const aiMotion = capabilities?.ai_motion;

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-line bg-surface px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Scene {sceneIndex + 1}</h2>
          {saving ? <Badge tone="accent">Saving…</Badge> : null}
        </div>
        {scene.note ? <p className="mt-0.5 text-xs text-faint">{scene.note}</p> : null}
      </header>

      <div className="space-y-6 p-4">
        {/* ------------------------------------------------------------ image */}
        <Section title="Image" icon={<Film className="h-3.5 w-3.5" />}>
          <Select
            label="Source image"
            value={scene.media_id ?? ""}
            onChange={(event) => onChange({ media_id: event.target.value || null })}
            options={[
              { value: "", label: "No image (colour card)" },
              ...images.map((image, index) => ({
                value: image.id,
                label: `${index + 1}. ${image.original_filename || "Image"}`,
              })),
            ]}
          />
          {!scene.media_id ? (
            <Notice tone="info" className="mt-2">
              This scene renders as a plain card — useful for a closing call to action.
            </Notice>
          ) : null}
        </Section>

        {/* ---------------------------------------------------------- timing */}
        <Section title="Timing">
          <Slider
            label="Duration"
            value={scene.duration}
            min={0.4}
            max={15}
            step={0.1}
            suffix="s"
            onChange={(value) => onChange({ duration: Number(value.toFixed(2)) })}
          />
        </Section>

        {/* ------------------------------------------------------- animation */}
        <Section title="Animation" icon={<Crosshair className="h-3.5 w-3.5" />}>
          <Select
            label="Camera move"
            value={scene.animation}
            onChange={(event) => onChange({ animation: event.target.value as AnimationType })}
            options={(options?.animations ?? []).map((value) => ({
              value,
              label: humanise(value),
            }))}
          />
          <Slider
            label="Intensity"
            value={scene.animation_intensity}
            min={0.3}
            max={2}
            step={0.05}
            onChange={(value) => onChange({ animation_intensity: Number(value.toFixed(2)) })}
          />

          <div className="mt-3">
            <span className="field-label">Focal point</span>
            <FocusPicker
              x={scene.focus_x}
              y={scene.focus_y}
              imageUrl={scene.media?.thumbnail_url ?? scene.media?.url ?? null}
              onChange={(x, y) =>
                onChange({ focus_x: Number(x.toFixed(3)), focus_y: Number(y.toFixed(3)) })
              }
            />
            <p className="mt-1.5 text-xs text-faint">
              Zooms and pans move towards this point. Detected automatically from the image.
            </p>
          </div>
        </Section>

        {/* ------------------------------------------------------ transition */}
        <Section title="Transition in">
          {isFirst ? (
            <Notice tone="info">The first scene opens on a cut — there is nothing to come from.</Notice>
          ) : (
            <>
              <Select
                label="Type"
                value={scene.transition}
                onChange={(event) => onChange({ transition: event.target.value as TransitionType })}
                options={(options?.transitions ?? []).map((value) => ({
                  value,
                  label: humanise(value),
                }))}
              />
              {scene.transition !== "none" ? (
                <Slider
                  label="Length"
                  value={scene.transition_duration}
                  min={0.1}
                  max={2}
                  step={0.05}
                  suffix="s"
                  onChange={(value) =>
                    onChange({ transition_duration: Number(value.toFixed(2)) })
                  }
                />
              ) : null}
            </>
          )}
        </Section>

        {/* ------------------------------------------------------------ text */}
        <Section
          title="Text"
          icon={<Type className="h-3.5 w-3.5" />}
          action={
            <Button size="sm" variant="ghost" onClick={addText} disabled={texts.length >= 4}>
              <Plus className="h-3.5 w-3.5" />
              Add
            </Button>
          }
        >
          {texts.length === 0 ? (
            <p className="text-xs text-faint">No text on this scene.</p>
          ) : (
            <>
              {texts.length > 1 ? (
                <div className="mb-3 flex gap-1">
                  {texts.map((text) => (
                    <button
                      key={text.id}
                      type="button"
                      onClick={() => selectText(text.id)}
                      className={cn(
                        "flex-1 truncate rounded-md border px-2 py-1 text-2xs",
                        text.id === activeText?.id
                          ? "border-accent bg-accent/10 text-accent"
                          : "border-line text-muted",
                      )}
                    >
                      {humanise(text.role)}
                    </button>
                  ))}
                </div>
              ) : null}

              {activeText ? (
                <div className="space-y-3">
                  <Textarea
                    label="Content"
                    value={activeText.content}
                    onChange={(event) => patchText(activeIndex, { content: event.target.value })}
                    maxLength={280}
                    className="min-h-[70px]"
                  />

                  <div className="grid grid-cols-2 gap-2">
                    <Select
                      label="Role"
                      value={activeText.role}
                      onChange={(event) =>
                        patchText(activeIndex, { role: event.target.value as TextRole })
                      }
                      options={(options?.text_roles ?? []).map((value) => ({
                        value,
                        label: humanise(value),
                      }))}
                    />
                    <Select
                      label="Position"
                      value={activeText.position}
                      onChange={(event) =>
                        patchText(activeIndex, { position: event.target.value as TextPosition })
                      }
                      options={(options?.text_positions ?? []).map((value) => ({
                        value,
                        label: humanise(value),
                      }))}
                    />
                    <Select
                      label="Animation"
                      value={activeText.animation}
                      onChange={(event) =>
                        patchText(activeIndex, { animation: event.target.value as TextAnimation })
                      }
                      options={(options?.text_animations ?? []).map((value) => ({
                        value,
                        label: humanise(value),
                      }))}
                    />
                    <Select
                      label="Alignment"
                      value={activeText.align}
                      onChange={(event) =>
                        patchText(activeIndex, {
                          align: event.target.value as TextOverlay["align"],
                        })
                      }
                      options={[
                        { value: "left", label: "Left" },
                        { value: "center", label: "Centre" },
                        { value: "right", label: "Right" },
                      ]}
                    />
                    <Select
                      label="Font"
                      value={activeText.font_family}
                      onChange={(event) =>
                        patchText(activeIndex, {
                          font_family: event.target.value as TextOverlay["font_family"],
                        })
                      }
                      options={(options?.font_families ?? []).map((value) => ({
                        value,
                        label: humanise(value),
                      }))}
                    />
                    <Select
                      label="Background"
                      value={activeText.background}
                      onChange={(event) =>
                        patchText(activeIndex, {
                          background: event.target.value as TextBackground,
                        })
                      }
                      options={(options?.text_backgrounds ?? []).map((value) => ({
                        value,
                        label: humanise(value),
                      }))}
                    />
                  </div>

                  <Slider
                    label="Size"
                    value={activeText.font_size}
                    min={16}
                    max={200}
                    step={2}
                    suffix="px"
                    onChange={(value) => patchText(activeIndex, { font_size: Math.round(value) })}
                  />
                  <Slider
                    label="Weight"
                    value={activeText.font_weight}
                    min={100}
                    max={900}
                    step={100}
                    onChange={(value) => patchText(activeIndex, { font_weight: Math.round(value) })}
                  />
                  <Slider
                    label="Letter spacing"
                    value={activeText.letter_spacing}
                    min={-5}
                    max={20}
                    step={0.5}
                    onChange={(value) => patchText(activeIndex, { letter_spacing: value })}
                  />
                  <Slider
                    label="Opacity"
                    value={activeText.opacity}
                    min={0}
                    max={1}
                    step={0.05}
                    onChange={(value) => patchText(activeIndex, { opacity: value })}
                  />
                  {activeText.background !== "none" ? (
                    <Slider
                      label="Background opacity"
                      value={activeText.background_opacity}
                      min={0}
                      max={1}
                      step={0.05}
                      onChange={(value) => patchText(activeIndex, { background_opacity: value })}
                    />
                  ) : null}

                  <div className="grid grid-cols-2 gap-2">
                    <ColourField
                      label="Text colour"
                      value={activeText.color}
                      onChange={(value) => patchText(activeIndex, { color: value })}
                    />
                    {activeText.background !== "none" ? (
                      <ColourField
                        label="Background"
                        value={activeText.background_color}
                        onChange={(value) => patchText(activeIndex, { background_color: value })}
                      />
                    ) : null}
                  </div>

                  <Slider
                    label="Appears at"
                    value={activeText.start}
                    min={0}
                    max={Math.max(0.1, scene.duration - 0.1)}
                    step={0.05}
                    suffix="s"
                    onChange={(value) => patchText(activeIndex, { start: value })}
                  />

                  <div className="space-y-1 border-t border-line pt-3">
                    <Toggle
                      label="Uppercase"
                      checked={activeText.uppercase}
                      onChange={(checked) => patchText(activeIndex, { uppercase: checked })}
                    />
                    <Toggle
                      label="Drop shadow"
                      checked={activeText.shadow}
                      onChange={(checked) => patchText(activeIndex, { shadow: checked })}
                    />
                  </div>

                  <Button
                    variant="danger"
                    size="sm"
                    className="w-full"
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                    onClick={() => removeText(activeIndex)}
                  >
                    Remove this text
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </Section>

        {/* -------------------------------------------------------- AI motion */}
        <Section title="AI Motion" icon={<Sparkles className="h-3.5 w-3.5" />}>
          {aiMotion?.available ? (
            <>
              <Textarea
                label="Motion prompt"
                value={aiPrompt}
                onChange={(event) => setAiPrompt(event.target.value)}
                placeholder="Slow push in, subtle fabric movement, cinematic light"
                maxLength={800}
                className="min-h-[60px]"
              />
              <Button
                size="sm"
                className="mt-2 w-full"
                disabled={!scene.media_id}
                onClick={() => onGenerateAiMotion(aiPrompt)}
              >
                Generate with {aiMotion.display_name}
              </Button>
              {scene.ai_motion?.generated_media_id ? (
                <Notice tone="success" className="mt-2">
                  A generated clip is attached to this scene and will be used when rendering.
                </Notice>
              ) : scene.ai_motion?.error ? (
                <Notice tone="danger" className="mt-2">
                  {scene.ai_motion.error}
                </Notice>
              ) : null}
            </>
          ) : (
            <Notice tone="warning">
              {aiMotion?.message ??
                "AI Motion is unavailable because no video generation provider is configured."}
            </Notice>
          )}
        </Section>
      </div>
    </div>
  );
}

function Section({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-faint">
          {icon}
          {title}
        </h3>
        {action}
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

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
    <div>
      <span className="field-label">{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
          className="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-line bg-elevated p-0.5"
          aria-label={label}
        />
        <Input
          value={value}
          onChange={(event) => {
            const next = event.target.value.toUpperCase();
            if (/^#[0-9A-F]{0,6}$/.test(next)) onChange(next);
          }}
          className="font-mono text-xs"
          maxLength={7}
          aria-label={`${label} hex value`}
        />
      </div>
    </div>
  );
}

/** Click anywhere on the thumbnail to set the point the camera moves towards. */
function FocusPicker({
  x,
  y,
  imageUrl,
  onChange,
}: {
  x: number;
  y: number;
  imageUrl: string | null;
  onChange: (x: number, y: number) => void;
}) {
  return (
    <button
      type="button"
      className="checkerboard relative block aspect-[9/16] w-full max-w-[120px] overflow-hidden rounded-lg border border-line"
      onClick={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        onChange(
          Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)),
          Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height)),
        );
      }}
      aria-label="Set the focal point"
    >
      {imageUrl ? (
        <img src={imageUrl} alt="" className="h-full w-full object-cover opacity-80" />
      ) : null}
      <span
        className="absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-accent shadow"
        style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
        aria-hidden
      />
    </button>
  );
}
