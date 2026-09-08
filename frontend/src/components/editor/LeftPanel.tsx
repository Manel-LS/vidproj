"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Images,
  LayoutTemplate,
  Music,
  Sparkles,
  Type,
  Upload,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select, Slider, Textarea, Toggle } from "@/components/ui/Field";
import { Badge, Notice, Spinner } from "@/components/ui/Feedback";
import { Dropzone } from "@/components/media/Dropzone";
import { MediaGrid } from "@/components/media/MediaGrid";
import { LanguageSelect } from "@/components/editor/LanguageSelect";
import { SubtitleStyleSelect } from "@/components/editor/SubtitleStyleSelect";
import { api } from "@/lib/api/client";
import type {
  Capabilities,
  EditorOptions,
  MediaItem,
  ProjectDetail,
  StylePreset,
  TemplateSummary,
  VideoStyleKey,
} from "@/lib/api/types";
import { useEditorStore, type LeftPanelTab } from "@/lib/store/editor";
import { cn } from "@/lib/utils";

const TABS: Array<{ key: LeftPanelTab; label: string; icon: typeof Images }> = [
  { key: "media", label: "Media", icon: Images },
  { key: "templates", label: "Templates", icon: LayoutTemplate },
  { key: "text", label: "Text", icon: Type },
  { key: "audio", label: "Audio", icon: Music },
  { key: "ai", label: "AI", icon: Sparkles },
];

export interface LeftPanelProps {
  project: ProjectDetail;
  capabilities: Capabilities | undefined;
  styles: StylePreset[];
  templates: TemplateSummary[];
  options: EditorOptions | undefined;
  images: MediaItem[];
  busy: boolean;
  uploadProgress: number;
  onUploadImages: (files: File[]) => void;
  onUploadAudio: (file: File) => void;
  onReorderImages: (ids: string[]) => void;
  onDeleteImage: (item: MediaItem) => void;
  onReplaceImage: (item: MediaItem, file: File) => void;
  onCropImage: (item: MediaItem) => void;
  onAddSceneFromImage: (item: MediaItem) => void;
  onApplyTemplate: (key: string) => void;
  onUpdateAudio: (changes: Record<string, unknown>) => void;
  onUpdateProject: (changes: Record<string, unknown>) => void;
  onGeneratePlan: (payload: {
    instruction: string;
    target_duration: number;
    include_voiceover: boolean;
    style: VideoStyleKey;
  }) => void;
  onDraftVoiceScript: () => void;
  onGenerateVoiceOver: () => void;
  onUpdateVoiceOver: (changes: Record<string, unknown>) => void;
  planning: boolean;
}

export function LeftPanel(props: LeftPanelProps) {
  const { leftTab, setLeftTab } = useEditorStore();

  return (
    <div className="flex h-full">
      <nav
        className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-line bg-surface py-3"
        aria-label="Editor tools"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = leftTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setLeftTab(tab.key)}
              aria-pressed={active}
              className={cn(
                "flex w-11 flex-col items-center gap-1 rounded-lg py-2 text-2xs transition-colors",
                active ? "bg-elevated text-accent" : "text-faint hover:bg-elevated/60 hover:text-ink",
              )}
            >
              <Icon className="h-[18px] w-[18px]" aria-hidden />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="flex-1 overflow-y-auto">
        {leftTab === "media" ? <MediaTab {...props} /> : null}
        {leftTab === "templates" ? <TemplatesTab {...props} /> : null}
        {leftTab === "text" ? <TextTab {...props} /> : null}
        {leftTab === "audio" ? <AudioTab {...props} /> : null}
        {leftTab === "ai" ? <AiTab {...props} /> : null}
      </div>
    </div>
  );
}

function PanelHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      {hint ? <p className="mt-0.5 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

// ------------------------------------------------------------------- media --

function MediaTab({
  images,
  capabilities,
  busy,
  uploadProgress,
  onUploadImages,
  onReorderImages,
  onDeleteImage,
  onReplaceImage,
  onCropImage,
  onAddSceneFromImage,
}: LeftPanelProps) {
  const replaceRef = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState<MediaItem | null>(null);

  return (
    <div className="p-4">
      <PanelHeader title="Media" hint="Each image can be used by any number of scenes." />

      <Dropzone
        compact
        onFiles={onUploadImages}
        uploading={busy}
        progress={uploadProgress}
        maxBytes={capabilities?.limits.max_image_bytes}
        maxFiles={capabilities?.limits.max_images_per_project ?? 20}
        label="Add images"
      />

      <div className="mt-4">
        {images.length === 0 ? (
          <p className="text-xs text-faint">No images yet.</p>
        ) : (
          <MediaGrid
            className="grid-cols-2 sm:grid-cols-2 md:grid-cols-2 xl:grid-cols-3"
            items={images}
            onReorder={onReorderImages}
            onDelete={onDeleteImage}
            onCrop={onCropImage}
            onReplace={(item) => {
              setReplacing(item);
              replaceRef.current?.click();
            }}
            onSelect={onAddSceneFromImage}
          />
        )}
      </div>

      <p className="mt-3 text-xs text-faint">
        Click an image to add it as a new scene at the end of the timeline.
      </p>

      <input
        ref={replaceRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file && replacing) onReplaceImage(replacing, file);
          event.target.value = "";
          setReplacing(null);
        }}
      />
    </div>
  );
}

// --------------------------------------------------------------- templates --

function TemplatesTab({ templates, project, onApplyTemplate, busy }: LeftPanelProps) {
  const [category, setCategory] = useState<string>("all");
  const categories = ["all", ...Array.from(new Set(templates.map((item) => item.category)))];
  const filtered =
    category === "all" ? templates : templates.filter((item) => item.category === category);

  return (
    <div className="p-4">
      <PanelHeader
        title="Templates"
        hint="Rebuilds your scenes from a proven structure. Your images stay put."
      />

      <div className="mb-3 flex flex-wrap gap-1">
        {categories.map((entry) => (
          <button
            key={entry}
            type="button"
            onClick={() => setCategory(entry)}
            className={cn(
              "rounded-pill border px-2 py-0.5 text-2xs transition-colors",
              category === entry
                ? "border-accent bg-accent/10 text-accent"
                : "border-line text-muted hover:text-ink",
            )}
          >
            {entry === "all" ? "All" : entry}
          </button>
        ))}
      </div>

      <ul className="space-y-2">
        {filtered.map((template) => {
          const active = project.template_key === template.key;
          const [from, to] = template.gradient;
          return (
            <li key={template.key}>
              <button
                type="button"
                onClick={() => onApplyTemplate(template.key)}
                disabled={busy}
                className={cn(
                  "flex w-full gap-3 rounded-xl border p-2.5 text-left transition-colors disabled:opacity-50",
                  active ? "border-accent bg-accent/8" : "border-line hover:border-accent/40",
                )}
              >
                <span
                  className="h-14 w-10 shrink-0 rounded-lg"
                  style={{ background: `linear-gradient(150deg, ${from}, ${to})` }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium text-ink">{template.name}</span>
                    {active ? <Badge tone="accent">Active</Badge> : null}
                  </span>
                  <span className="mt-0.5 line-clamp-2 block text-xs text-muted">
                    {template.description}
                  </span>
                  <span className="mt-1 block text-2xs text-faint">
                    {template.category} · ~{template.recommended_duration}s · needs{" "}
                    {template.min_images}+ images
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// -------------------------------------------------------------------- text --

function TextTab({ project, onUpdateProject, busy }: LeftPanelProps) {
  const [hook, setHook] = useState(project.hook);
  const [cta, setCta] = useState(project.cta);
  const [caption, setCaption] = useState(project.caption);
  const [hashtags, setHashtags] = useState(project.hashtags.join(" "));

  return (
    <div className="p-4">
      <PanelHeader
        title="Copy"
        hint="The hook and CTA feed the planner; the caption is for the post itself."
      />

      <div className="space-y-4">
        <Input
          label="Hook"
          value={hook}
          onChange={(event) => setHook(event.target.value)}
          onBlur={() => hook !== project.hook && onUpdateProject({ hook })}
          placeholder="Looking for the perfect school supplies?"
          maxLength={300}
        />
        <Input
          label="Call to action"
          value={cta}
          onChange={(event) => setCta(event.target.value)}
          onBlur={() => cta !== project.cta && onUpdateProject({ cta })}
          placeholder="Shop now"
          maxLength={300}
        />
        <Textarea
          label="Social caption"
          value={caption}
          onChange={(event) => setCaption(event.target.value)}
          onBlur={() => caption !== project.caption && onUpdateProject({ caption })}
          maxLength={2200}
          hint="Copied alongside the video when you export."
        />
        <Input
          label="Hashtags"
          value={hashtags}
          onChange={(event) => setHashtags(event.target.value)}
          onBlur={() => {
            const parsed = hashtags.split(/[\s,]+/).map((tag) => tag.replace(/^#/, "")).filter(Boolean);
            if (parsed.join(" ") !== project.hashtags.join(" ")) {
              onUpdateProject({ hashtags: parsed });
            }
          }}
          placeholder="backtoschool stationery fyp"
          hint="Space separated. The # is added for you."
        />

        {project.hashtags.length ? (
          <div className="flex flex-wrap gap-1">
            {project.hashtags.map((tag) => (
              <Badge key={tag}>#{tag}</Badge>
            ))}
          </div>
        ) : null}
      </div>

      <p className="mt-5 text-xs text-faint">
        To edit the words that appear <em>on screen</em>, select a scene and use the Text
        section in the panel on the right.
      </p>

      {busy ? <Spinner className="mt-3" /> : null}
    </div>
  );
}

// ------------------------------------------------------------------- audio --

function AudioTab({
  project,
  capabilities,
  busy,
  uploadProgress,
  onUploadAudio,
  onUpdateAudio,
}: LeftPanelProps) {
  const audio = project.audio;

  return (
    <div className="p-4">
      <PanelHeader title="Audio" hint="Music is trimmed and faded to your video's length." />

      <Dropzone
        compact
        accept={["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"]}
        maxBytes={capabilities?.limits.max_audio_bytes ?? 25 * 1024 * 1024}
        maxFiles={1}
        uploading={busy}
        progress={uploadProgress}
        label="Add music"
        hint="MP3 or WAV"
        onFiles={(files) => files[0] && onUploadAudio(files[0])}
      />

      {audio?.media ? (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-2 rounded-lg border border-line bg-elevated px-3 py-2">
            <Music className="h-4 w-4 shrink-0 text-positive" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs text-ink">
                {audio.media.original_filename}
              </span>
              {audio.media.duration_seconds ? (
                <span className="block text-2xs text-faint">
                  {audio.media.duration_seconds.toFixed(1)}s source
                </span>
              ) : null}
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onUpdateAudio({ clear: true })}
              aria-label="Remove music"
            >
              Remove
            </Button>
          </div>

          <audio controls src={audio.media.url} className="w-full" preload="none">
            Your browser cannot play this audio file.
          </audio>

          <Slider
            label="Volume"
            value={audio.volume}
            min={0}
            max={1.5}
            step={0.05}
            onChange={(value) => onUpdateAudio({ volume: value })}
          />
          <Slider
            label="Fade in"
            value={audio.fade_in}
            min={0}
            max={5}
            step={0.1}
            suffix="s"
            onChange={(value) => onUpdateAudio({ fade_in: value })}
          />
          <Slider
            label="Fade out"
            value={audio.fade_out}
            min={0}
            max={5}
            step={0.1}
            suffix="s"
            onChange={(value) => onUpdateAudio({ fade_out: value })}
          />
          <Slider
            label="Start at"
            value={audio.start_offset}
            min={0}
            max={Math.max(0, (audio.media.duration_seconds ?? 30) - 1)}
            step={0.5}
            suffix="s"
            onChange={(value) => onUpdateAudio({ start_offset: value })}
          />
          <Toggle
            label="Loop to fill the video"
            hint="A short track repeats instead of falling silent."
            checked={audio.loop}
            onChange={(checked) => onUpdateAudio({ loop: checked })}
          />
        </div>
      ) : (
        <Notice tone="info" className="mt-4">
          No music yet. Reelcraft ships no built-in library — upload a track you have the
          rights to use.
        </Notice>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------- ai --

function AiTab({
  project,
  capabilities,
  options,
  styles,
  planning,
  busy,
  onGeneratePlan,
  onDraftVoiceScript,
  onGenerateVoiceOver,
  onUpdateVoiceOver,
  onUpdateProject,
}: LeftPanelProps) {
  const [instruction, setInstruction] = useState("");
  const [duration, setDuration] = useState(
    project.target_duration ?? Math.max(6, Math.round(project.total_duration || 15)),
  );
  const [style, setStyle] = useState<VideoStyleKey>(project.style);
  const [includeVoice, setIncludeVoice] = useState(project.voice_over?.enabled ?? false);
  const [script, setScript] = useState(project.voice_over?.script ?? "");

  const planner = capabilities?.ai_planner;
  const voice = capabilities?.voiceover;
  const voiceStatus = project.voice_over?.status;

  return (
    <div className="p-4">
      <PanelHeader
        title="AI assistant"
        hint={
          planner?.available
            ? `Planning with ${planner.display_name}.`
            : "No AI provider configured — the built-in planner will structure your video."
        }
      />

      {!planner?.available && planner?.message ? (
        <Notice tone="warning" className="mb-4">
          {planner.message}
        </Notice>
      ) : null}

      <div className="space-y-4">
        <Textarea
          label="What should this video do?"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder="Create a 15 second TikTok promoting these school supplies. Make it energetic and modern."
          maxLength={1000}
          className="min-h-[84px]"
        />

        {/* Persisted immediately rather than sent with the plan request: it also
            drives the voice and the subtitle direction, which are used outside
            planning. */}
        <LanguageSelect
          value={project.language}
          capabilities={capabilities}
          disabled={busy}
          onChange={(language) => onUpdateProject({ language })}
        />

        <CharacterPicker
          project={project}
          disabled={busy}
          onChange={(characterId) => onUpdateProject({ character_id: characterId })}
        />

        <SubtitleStyleSelect
          project={project}
          options={options?.subtitle_styles}
          capabilities={capabilities}
          disabled={busy}
          onChange={(subtitle_style) => onUpdateProject({ subtitle_style })}
        />

        <Select
          label="Style"
          value={style}
          onChange={(event) => setStyle(event.target.value as VideoStyleKey)}
          options={styles.map((preset) => ({ value: preset.key, label: preset.name }))}
        />

        <Slider
          label="Target length"
          value={duration}
          min={5}
          max={90}
          step={1}
          suffix="s"
          onChange={(value) => setDuration(Math.round(value))}
        />

        <Toggle
          label="Include a voice-over script"
          checked={includeVoice}
          onChange={setIncludeVoice}
        />

        <Button
          className="w-full"
          loading={planning}
          icon={planner?.available ? <Sparkles className="h-4 w-4" /> : <Wand2 className="h-4 w-4" />}
          onClick={() =>
            onGeneratePlan({
              instruction,
              target_duration: duration,
              include_voiceover: includeVoice,
              style,
            })
          }
        >
          {planner?.available ? "Create with AI" : "Rebuild my plan"}
        </Button>

        <p className="text-xs text-faint">
          This replaces every scene. Your images and music are kept.
        </p>
      </div>

      {/* --------------------------------------------------------- voice-over */}
      <div className="mt-7 border-t border-line pt-5">
        <PanelHeader
          title="Voice-over"
          hint={voice?.available ? `Synthesised with ${voice.display_name}.` : undefined}
        />

        {!voice?.available ? (
          <Notice tone="warning">{voice?.message ?? "No text-to-speech provider is configured."}</Notice>
        ) : null}

        <Textarea
          label="Script"
          value={script}
          onChange={(event) => setScript(event.target.value)}
          onBlur={() => script !== project.voice_over?.script && onUpdateVoiceOver({ script })}
          placeholder="Looking for the perfect school supplies? Everything you need, in one place."
          maxLength={4000}
          className="min-h-[90px]"
        />

        <div className="mt-2 flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="flex-1"
            onClick={onDraftVoiceScript}
            icon={<Wand2 className="h-3.5 w-3.5" />}
          >
            Draft from scenes
          </Button>
          <Button
            size="sm"
            className="flex-1"
            disabled={!voice?.available || !script.trim()}
            loading={voiceStatus === "generating"}
            onClick={onGenerateVoiceOver}
            icon={<Upload className="h-3.5 w-3.5" />}
          >
            Generate audio
          </Button>
        </div>

        {voiceStatus === "ready" && project.voice_over?.media ? (
          <>
            <Notice tone="success" className="mt-3">
              Voice-over ready — it is mixed under the music when you render.
            </Notice>
            <audio controls src={project.voice_over.media.url} className="mt-2 w-full" preload="none" />
          </>
        ) : null}
        {voiceStatus === "failed" && project.voice_over?.error ? (
          <Notice tone="danger" className="mt-3">
            {project.voice_over.error}
          </Notice>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Attaching a saved character to this project.
 *
 * A character crosses projects, so the list is fetched here rather than threaded
 * through the editor's project query. Detaching sends an explicit null — which is
 * the one field on the project endpoint where null means "clear it" rather than
 * "unchanged".
 */
function CharacterPicker({
  project,
  disabled,
  onChange,
}: {
  project: ProjectDetail;
  disabled?: boolean;
  onChange: (characterId: string | null) => void;
}) {
  const characters = useQuery({ queryKey: ["characters"], queryFn: api.listCharacters });
  const items = characters.data ?? [];

  if (!items.length) {
    return (
      <div className="rounded-xl border border-dashed border-line px-3 py-2.5">
        <p className="text-xs text-muted">
          Save a character in{" "}
          <Link href="/characters" className="text-accent hover:underline">
            Characters
          </Link>{" "}
          to keep the same face across your videos.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Select
        label="Character"
        hint="Its saved description is replayed into every generated image."
        value={project.character_id ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        options={[
          { value: "", label: "No character" },
          ...items.map((character) => ({ value: character.id, label: character.name })),
        ]}
      />
      {project.character_description ? (
        <p className="text-2xs italic text-faint">
          the same {project.character_description}
        </p>
      ) : null}
    </div>
  );
}
