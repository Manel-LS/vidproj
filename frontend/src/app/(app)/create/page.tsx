"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea, Toggle } from "@/components/ui/Field";
import { Notice, Spinner } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { Dropzone } from "@/components/media/Dropzone";
import { MediaGrid } from "@/components/media/MediaGrid";
import { StyleCard } from "@/components/styles/StyleCard";
import { LanguageSelect } from "@/components/editor/LanguageSelect";
import { api, ApiError } from "@/lib/api/client";
import type { Language, MediaItem, Platform, ProjectDetail, VideoStyleKey } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "details", label: "Project" },
  { key: "images", label: "Images" },
  { key: "style", label: "Style" },
  { key: "plan", label: "AI plan" },
] as const;

type StepKey = (typeof STEPS)[number]["key"];

const EXAMPLE_TOPICS = [
  "New school supplies collection",
  "Summer fashion products",
  "Restaurant promotion",
  "Real estate property",
];

export default function CreatePage() {
  return (
    <Suspense fallback={<div className="p-10"><Spinner label="Loading…" /></div>}>
      <CreateWizard />
    </Suspense>
  );
}

function CreateWizard() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();

  const [step, setStep] = useState<StepKey>("details");
  const [project, setProject] = useState<ProjectDetail | null>(null);

  // Step 1
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [platform, setPlatform] = useState<Platform>("tiktok");
  const [language, setLanguage] = useState<Language>("en");

  // Step 2
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Step 3
  const [style, setStyle] = useState<VideoStyleKey>(
    (params.get("style") as VideoStyleKey) ?? "product_showcase",
  );
  const templateKey = params.get("template");

  // Step 4
  const [instruction, setInstruction] = useState("");
  const [duration, setDuration] = useState(15);
  const [wantVoiceOver, setWantVoiceOver] = useState(false);

  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const styles = useQuery({ queryKey: ["styles"], queryFn: api.styles });
  const formats = useQuery({ queryKey: ["formats"], queryFn: api.formats });

  const aiAvailable = capabilities.data?.ai_planner.available ?? false;
  const voiceAvailable = capabilities.data?.voiceover.available ?? false;
  const maxImageBytes = capabilities.data?.limits.max_image_bytes ?? 15 * 1024 * 1024;

  const createProject = useMutation({
    mutationFn: () =>
      api.createProject({
        name: name.trim(),
        description: description.trim(),
        topic: description.trim().slice(0, 300) || name.trim(),
        platform,
        language,
        style,
        template_key: templateKey,
        target_duration: duration,
      }),
    onSuccess: (created) => {
      setProject(created);
      setStep("images");
    },
    onError: (error) => toast.fromError(error),
  });

  const uploadImages = useMutation({
    mutationFn: async (files: File[]) => {
      if (!project) throw new ApiError(0, "no_project", "Create the project first.");
      return api.uploadImages(project.id, files, setUploadProgress);
    },
    onSuccess: (uploaded) => {
      setMedia((current) => [...current, ...uploaded]);
      setUploadProgress(0);
      toast.success(
        `${uploaded.length} image${uploaded.length === 1 ? "" : "s"} uploaded`,
        "A scene was created for each one.",
      );
    },
    onError: (error) => {
      setUploadProgress(0);
      toast.fromError(error);
    },
  });

  const generatePlan = useMutation({
    mutationFn: async () => {
      if (!project) throw new ApiError(0, "no_project", "Create the project first.");
      await api.updateProject(project.id, { style, target_duration: duration });
      return api.generatePlan(project.id, {
        instruction,
        style,
        template_key: templateKey,
        target_duration: duration,
        include_voiceover: wantVoiceOver && voiceAvailable,
        use_ai: true,
        apply: true,
      });
    },
    onSuccess: (result) => {
      if (result.notice) toast.info("Plan ready", result.notice);
      else toast.success("Your video plan is ready.", `${result.plan.scenes.length} scenes · ${result.total_duration.toFixed(1)}s`);
      router.push(`/editor/${project!.id}`);
    },
    onError: (error) => toast.fromError(error),
  });

  const skipToEditor = () => project && router.push(`/editor/${project.id}`);

  const stepIndex = STEPS.findIndex((entry) => entry.key === step);
  const canContinue = useMemo(() => {
    if (step === "details") return name.trim().length > 0;
    if (step === "images") return media.length > 0;
    return true;
  }, [step, name, media.length]);

  const handleFiles = useCallback(
    (files: File[]) => {
      uploadImages.mutate(files);
    },
    [uploadImages],
  );

  return (
    <div className="mx-auto max-w-4xl px-5 py-8 lg:px-8">
      <button
        type="button"
        onClick={() => (stepIndex === 0 ? router.push("/dashboard") : setStep(STEPS[stepIndex - 1].key))}
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        {stepIndex === 0 ? "Back to projects" : `Back to ${STEPS[stepIndex - 1].label.toLowerCase()}`}
      </button>

      {/* Stepper */}
      <ol className="mb-8 flex items-center gap-2" aria-label="Progress">
        {STEPS.map((entry, index) => {
          const done = index < stepIndex;
          const active = index === stepIndex;
          return (
            <li key={entry.key} className="flex flex-1 items-center gap-2">
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors",
                  done
                    ? "bg-accent text-white"
                    : active
                      ? "bg-accent/20 text-accent ring-2 ring-accent"
                      : "bg-elevated text-faint",
                )}
                aria-current={active ? "step" : undefined}
              >
                {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : index + 1}
              </span>
              <span className={cn("hidden text-sm sm:block", active ? "text-ink" : "text-faint")}>
                {entry.label}
              </span>
              {index < STEPS.length - 1 ? (
                <span className={cn("h-px flex-1", done ? "bg-accent" : "bg-line")} />
              ) : null}
            </li>
          );
        })}
      </ol>

      {/* ------------------------------------------------------ step: details */}
      {step === "details" ? (
        <section className="animate-fade-in">
          <h1 className="text-2xl font-semibold tracking-tight">Create a video</h1>
          <p className="mt-1.5 text-sm text-muted">
            Tell us what this is for. Everything here can be changed later.
          </p>

          <div className="mt-7 space-y-5">
            <Input
              label="Project name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="New school supplies collection"
              maxLength={160}
              autoFocus
            />

            <div>
              <Textarea
                label="What is the video about? (optional)"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Back-to-school stationery range. Colourful, aimed at parents shopping in late August."
                maxLength={4000}
                hint="The planner uses this to write your captions and pick the pacing."
              />
              <div className="mt-2 flex flex-wrap gap-1.5">
                {EXAMPLE_TOPICS.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => {
                      if (!name.trim()) setName(example);
                      setDescription(example);
                    }}
                    className="rounded-pill border border-line px-2.5 py-1 text-xs text-muted transition-colors hover:border-accent/50 hover:text-ink"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>

            <Select
              label="Where is it going?"
              value={platform}
              onChange={(event) => setPlatform(event.target.value as Platform)}
              options={(formats.data?.platforms ?? []).map((entry) => ({
                value: entry.key,
                label: `${entry.label} · ${entry.default_format} · up to ${entry.max_seconds}s`,
              }))}
              hint="All four use a 1080 × 1920 vertical frame by default."
            />

            <LanguageSelect
              value={language}
              capabilities={capabilities.data}
              onChange={setLanguage}
            />
          </div>

          <div className="mt-8 flex justify-end">
            <Button
              size="lg"
              disabled={!canContinue}
              loading={createProject.isPending}
              onClick={() => createProject.mutate()}
              icon={<ArrowRight className="h-4 w-4" />}
            >
              Continue
            </Button>
          </div>
        </section>
      ) : null}

      {/* ------------------------------------------------------- step: images */}
      {step === "images" ? (
        <section className="animate-fade-in">
          <h1 className="text-2xl font-semibold tracking-tight">Add your images</h1>
          <p className="mt-1.5 text-sm text-muted">
            Each image becomes a scene. Drag to reorder — the first one is your hook.
          </p>

          <Dropzone
            className="mt-6"
            onFiles={handleFiles}
            maxBytes={maxImageBytes}
            maxFiles={capabilities.data?.limits.max_images_per_project ?? 20}
            uploading={uploadImages.isPending}
            progress={uploadProgress}
            hint={`JPG, PNG or WEBP · up to ${Math.round(maxImageBytes / (1024 * 1024))} MB each`}
          />

          {media.length > 0 ? (
            <div className="mt-6">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-medium text-ink">
                  {media.length} image{media.length === 1 ? "" : "s"}
                </h2>
                <span className="text-xs text-faint">Drag the handle to reorder</span>
              </div>
              <MediaGrid
                items={media}
                sceneNumbers={Object.fromEntries(media.map((item, index) => [item.id, index + 1]))}
                onReorder={(ids) => {
                  if (!project) return;
                  setMedia((current) => ids.map((id) => current.find((item) => item.id === id)!).filter(Boolean));
                  api.reorderMedia(project.id, ids).catch((error) => toast.fromError(error));
                }}
                onDelete={(item) => {
                  if (!project) return;
                  setMedia((current) => current.filter((entry) => entry.id !== item.id));
                  api.deleteMedia(project.id, item.id).catch((error) => toast.fromError(error));
                }}
                onReplace={() => toast.info("Replace images in the editor", "The editor has the full media panel.")}
                onCrop={() => toast.info("Crop images in the editor", "The editor has the crop tool.")}
              />
            </div>
          ) : (
            <Notice tone="info" className="mt-5">
              Please upload at least one image to continue.
            </Notice>
          )}

          <div className="mt-8 flex justify-end gap-2">
            <Button variant="ghost" onClick={skipToEditor}>
              Skip to editor
            </Button>
            <Button
              size="lg"
              disabled={!canContinue}
              onClick={() => setStep("style")}
              icon={<ArrowRight className="h-4 w-4" />}
            >
              Choose a style
            </Button>
          </div>
        </section>
      ) : null}

      {/* -------------------------------------------------------- step: style */}
      {step === "style" ? (
        <section className="animate-fade-in">
          <h1 className="text-2xl font-semibold tracking-tight">Pick a style</h1>
          <p className="mt-1.5 text-sm text-muted">
            The style sets the pacing, the camera moves, the transitions and the typography.
          </p>

          {styles.isLoading ? (
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {Array.from({ length: 8 }).map((_, index) => (
                <div key={index} className="skeleton aspect-[4/5] rounded-card" />
              ))}
            </div>
          ) : (
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {(styles.data ?? []).map((preset) => (
                <StyleCard
                  key={preset.key}
                  preset={preset}
                  selected={style === preset.key}
                  onSelect={setStyle}
                />
              ))}
            </div>
          )}

          <div className="mt-8 flex justify-end">
            <Button size="lg" onClick={() => setStep("plan")} icon={<ArrowRight className="h-4 w-4" />}>
              Continue
            </Button>
          </div>
        </section>
      ) : null}

      {/* --------------------------------------------------------- step: plan */}
      {step === "plan" ? (
        <section className="animate-fade-in">
          <h1 className="text-2xl font-semibold tracking-tight">Let the planner build it</h1>
          <p className="mt-1.5 text-sm text-muted">
            You get a scene-by-scene plan you can edit before rendering.
          </p>

          {!aiAvailable ? (
            <Notice tone="warning" title="AI planning is not configured" className="mt-5">
              {capabilities.data?.ai_planner.message ??
                "The built-in planner will structure your video instead."}
            </Notice>
          ) : null}

          <div className="mt-6 space-y-5">
            <Textarea
              label="Tell the planner what you want"
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="Create a 15 second TikTok promoting these school supplies. Make it energetic and modern."
              maxLength={1000}
              hint="Optional. Mention tone, audience, offers or a deadline."
            />

            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-2xs font-medium uppercase tracking-wider text-faint">
                  Target length
                </span>
                <span className="font-mono text-xs tabular-nums text-muted">{duration}s</span>
              </div>
              <input
                type="range"
                min={5}
                max={60}
                step={1}
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
                aria-label="Target length in seconds"
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none
                  [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
                  [&::-webkit-slider-thumb]:bg-accent"
                style={{
                  background: `linear-gradient(to right, rgb(var(--accent)) ${((duration - 5) / 55) * 100}%, rgb(var(--line)) ${((duration - 5) / 55) * 100}%)`,
                }}
              />
            </div>

            <div className="rounded-xl border border-line bg-surface px-4 py-3">
              <Toggle
                label="Generate a voice-over script"
                hint={
                  voiceAvailable
                    ? "You can edit the script and synthesise it in the editor."
                    : capabilities.data?.voiceover.message ?? "No text-to-speech provider is configured."
                }
                checked={wantVoiceOver && voiceAvailable}
                onChange={setWantVoiceOver}
                disabled={!voiceAvailable}
              />
            </div>
          </div>

          <div className="mt-8 flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={skipToEditor}>
              Skip — I&apos;ll build it myself
            </Button>
            <Button
              size="lg"
              loading={generatePlan.isPending}
              onClick={() => generatePlan.mutate()}
              icon={aiAvailable ? <Sparkles className="h-4 w-4" /> : <Wand2 className="h-4 w-4" />}
            >
              {aiAvailable ? "Create with AI" : "Build my plan"}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
