"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  Film,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge, Notice, Spinner } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { CropModal } from "@/components/media/CropModal";
import { LeftPanel } from "@/components/editor/LeftPanel";
import { PreviewStage } from "@/components/editor/PreviewStage";
import { RenderDialog } from "@/components/editor/RenderDialog";
import { SceneProperties } from "@/components/editor/SceneProperties";
import { Timeline } from "@/components/editor/Timeline";
import { api, ApiError } from "@/lib/api/client";
import type { MediaItem, Scene, VideoStyleKey } from "@/lib/api/types";
import { useEditorStore } from "@/lib/store/editor";
import { cn, formatDuration } from "@/lib/utils";

export default function EditorPage() {
  // `useSearchParams` needs a Suspense boundary during prerender.
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center">
          <Spinner label="Opening your project…" />
        </div>
      }
    >
      <Editor />
    </Suspense>
  );
}

function Editor() {
  const params = useParams<{ projectId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();

  const projectId = params.projectId;
  const {
    selectedSceneId,
    select,
    reset,
    leftOpen,
    rightOpen,
    toggleLeft,
    toggleRight,
  } = useEditorStore();

  const [renderJobId, setRenderJobId] = useState<string | null>(searchParams.get("job"));
  const [renderOpen, setRenderOpen] = useState(Boolean(searchParams.get("job")));
  const [cropTarget, setCropTarget] = useState<MediaItem | null>(null);
  const [pendingSceneDelete, setPendingSceneDelete] = useState<Scene | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  useEffect(() => () => reset(), [reset]);

  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });

  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });
  const options = useQuery({ queryKey: ["options"], queryFn: api.options });
  const styles = useQuery({ queryKey: ["styles"], queryFn: api.styles });
  const templates = useQuery({ queryKey: ["templates"], queryFn: () => api.templates() });

  const refresh = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
    [queryClient, projectId],
  );

  const data = project.data;
  const scenes = useMemo(() => data?.scenes ?? [], [data]);
  const images = useMemo(() => (data?.media ?? []).filter((item) => item.kind === "image"), [data]);

  // Select the first scene once the project arrives.
  useEffect(() => {
    if (scenes.length && !scenes.some((scene) => scene.id === selectedSceneId)) {
      select(scenes[0].id);
    }
  }, [scenes, selectedSceneId, select]);

  const selectedScene = scenes.find((scene) => scene.id === selectedSceneId) ?? null;
  const selectedIndex = selectedScene ? scenes.indexOf(selectedScene) : 0;

  // ------------------------------------------------------------- mutations --

  const updateScene = useMutation({
    mutationFn: ({ sceneId, changes }: { sceneId: string; changes: Record<string, unknown> }) =>
      api.updateScene(projectId, sceneId, changes),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const reorderScenes = useMutation({
    mutationFn: (ids: string[]) => api.reorderScenes(projectId, ids),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const duplicateScene = useMutation({
    mutationFn: (scene: Scene) => api.duplicateScene(projectId, scene.id),
    onSuccess: () => {
      toast.success("Scene duplicated");
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const deleteScene = useMutation({
    mutationFn: (scene: Scene) => api.deleteScene(projectId, scene.id),
    onSuccess: () => {
      setPendingSceneDelete(null);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const addScene = useMutation({
    mutationFn: (mediaId: string | null) => api.createScene(projectId, { media_id: mediaId }),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const uploadImages = useMutation({
    mutationFn: (files: File[]) => api.uploadImages(projectId, files, setUploadProgress),
    onSuccess: (uploaded) => {
      setUploadProgress(0);
      toast.success(`${uploaded.length} image${uploaded.length === 1 ? "" : "s"} added`);
      void refresh();
    },
    onError: (error) => {
      setUploadProgress(0);
      toast.fromError(error);
    },
  });

  const uploadAudio = useMutation({
    mutationFn: (file: File) => api.uploadAudio(projectId, file, setUploadProgress),
    onSuccess: () => {
      setUploadProgress(0);
      toast.success("Music added");
      void refresh();
    },
    onError: (error) => {
      setUploadProgress(0);
      toast.fromError(error);
    },
  });

  const updateAudio = useMutation({
    mutationFn: (changes: Record<string, unknown>) => api.updateAudio(projectId, changes),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const updateProject = useMutation({
    mutationFn: (changes: Record<string, unknown>) => api.updateProject(projectId, changes),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const reorderImages = useMutation({
    mutationFn: (ids: string[]) => api.reorderMedia(projectId, ids),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const deleteImage = useMutation({
    mutationFn: (item: MediaItem) => api.deleteMedia(projectId, item.id),
    onSuccess: () => {
      toast.success("Image removed", "Scenes using it kept their timing and text.");
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const replaceImage = useMutation({
    mutationFn: ({ item, file }: { item: MediaItem; file: File }) =>
      api.replaceImage(projectId, item.id, file, setUploadProgress),
    onSuccess: () => {
      setUploadProgress(0);
      toast.success("Image replaced");
      void refresh();
    },
    onError: (error) => {
      setUploadProgress(0);
      toast.fromError(error);
    },
  });

  const cropImage = useMutation({
    mutationFn: ({ item, rect }: { item: MediaItem; rect: { x: number; y: number; width: number; height: number } }) =>
      api.cropMedia(projectId, item.id, rect),
    onSuccess: () => {
      setCropTarget(null);
      toast.success("Image cropped");
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const applyTemplate = useMutation({
    mutationFn: (key: string) => api.applyTemplate(projectId, key),
    onSuccess: (updated) => {
      toast.success("Template applied", `${updated.scenes.length} scenes rebuilt.`);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const generatePlan = useMutation({
    mutationFn: (payload: {
      instruction: string;
      target_duration: number;
      include_voiceover: boolean;
      style: VideoStyleKey;
    }) =>
      api.generatePlan(projectId, {
        instruction: payload.instruction,
        style: payload.style,
        target_duration: payload.target_duration,
        include_voiceover: payload.include_voiceover,
        use_ai: true,
        apply: true,
      }),
    onSuccess: (result) => {
      if (result.notice) toast.info("Plan ready", result.notice);
      else
        toast.success(
          "Your video plan is ready.",
          `${result.plan.scenes.length} scenes · ${result.total_duration.toFixed(1)}s`,
        );
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const draftVoiceScript = useMutation({
    mutationFn: () => api.draftVoiceOverScript(projectId),
    onSuccess: () => {
      toast.success("Script drafted from your scenes");
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const generateVoiceOver = useMutation({
    mutationFn: () => api.generateVoiceOver(projectId),
    onSuccess: () => {
      toast.info("Generating the voice-over…");
      window.setTimeout(() => void refresh(), 4000);
    },
    onError: (error) => toast.fromError(error),
  });

  const updateVoiceOver = useMutation({
    mutationFn: (changes: Record<string, unknown>) => api.updateVoiceOver(projectId, changes),
    onSuccess: () => refresh(),
    onError: (error) => toast.fromError(error),
  });

  const generateAiMotion = useMutation({
    mutationFn: ({ sceneId, prompt }: { sceneId: string; prompt: string }) =>
      api.generateAiMotion(projectId, sceneId, prompt),
    onSuccess: (result) => toast.info("AI Motion queued", result.message),
    onError: (error) => toast.fromError(error),
  });

  const startRender = useMutation({
    mutationFn: () => api.startRender(projectId),
    onSuccess: (job) => {
      setRenderJobId(job.id);
      setRenderOpen(true);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  // ------------------------------------------------------------------ view --

  if (project.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Opening your project…" />
      </div>
    );
  }

  if (project.isError || !data) {
    const notFound = project.error instanceof ApiError && project.error.status === 404;
    return (
      <div className="mx-auto max-w-md px-6 py-20">
        <Notice tone="danger" title={notFound ? "Project not found" : "Could not open this project"}>
          {project.error instanceof Error ? project.error.message : "Please try again."}
        </Notice>
        <Button className="mt-4" variant="secondary" onClick={() => router.push("/dashboard")}>
          Back to projects
        </Button>
      </div>
    );
  }

  const busy =
    uploadImages.isPending ||
    uploadAudio.isPending ||
    replaceImage.isPending ||
    applyTemplate.isPending;

  const renderDisabled = scenes.length === 0 || !capabilities.data?.render.available;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* ------------------------------------------------------------ top bar */}
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-3">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-muted transition-colors hover:bg-elevated hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">Projects</span>
        </Link>

        <div className="min-w-0 flex-1">
          <input
            defaultValue={data.name}
            onBlur={(event) => {
              const next = event.target.value.trim();
              if (next && next !== data.name) updateProject.mutate({ name: next });
            }}
            className="w-full max-w-xs truncate rounded-lg bg-transparent px-2 py-1 text-sm font-medium text-ink outline-none transition-colors hover:bg-elevated focus:bg-elevated"
            aria-label="Project name"
            maxLength={160}
          />
        </div>

        <div className="hidden items-center gap-2 text-xs text-faint md:flex">
          <Badge>{data.format}</Badge>
          <Badge>{formatDuration(data.total_duration)}</Badge>
          <Badge>{scenes.length} scenes</Badge>
          {data.plan_generated_by !== "manual" ? (
            <Badge tone="accent">
              <Sparkles className="h-3 w-3" aria-hidden />
              {data.plan_generated_by === "heuristic" ? "Built-in planner" : data.plan_generated_by}
            </Badge>
          ) : null}
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleLeft}
            aria-label={leftOpen ? "Hide the tools panel" : "Show the tools panel"}
            className="hidden lg:inline-flex"
          >
            {leftOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleRight}
            aria-label={rightOpen ? "Hide the properties panel" : "Show the properties panel"}
            className="hidden lg:inline-flex"
          >
            {rightOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </Button>

          {data.download_url ? (
            <Button
              variant="secondary"
              size="sm"
              icon={<Download className="h-4 w-4" />}
              onClick={() => window.open(data.download_url!, "_blank")}
            >
              <span className="hidden sm:inline">Export</span>
            </Button>
          ) : null}

          <Button
            size="sm"
            icon={<Film className="h-4 w-4" />}
            loading={startRender.isPending}
            disabled={renderDisabled}
            onClick={() => startRender.mutate()}
            title={
              renderDisabled
                ? capabilities.data?.render.message || "Add at least one scene to render."
                : undefined
            }
          >
            Render
          </Button>
        </div>
      </header>

      {!capabilities.data?.render.available && capabilities.data?.render.message ? (
        <Notice tone="danger" className="mx-3 mt-3">
          {capabilities.data.render.message}
        </Notice>
      ) : null}

      {/* ------------------------------------------------------------- body */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside
          className={cn(
            "shrink-0 overflow-hidden border-r border-line bg-surface transition-[width]",
            leftOpen ? "w-full lg:w-[340px]" : "hidden lg:block lg:w-14",
          )}
        >
          <LeftPanel
            project={data}
            capabilities={capabilities.data}
            styles={styles.data ?? []}
            templates={templates.data?.items ?? []}
            images={images}
            busy={busy}
            uploadProgress={uploadProgress}
            planning={generatePlan.isPending}
            onUploadImages={(files) => uploadImages.mutate(files)}
            onUploadAudio={(file) => uploadAudio.mutate(file)}
            onReorderImages={(ids) => reorderImages.mutate(ids)}
            onDeleteImage={(item) => deleteImage.mutate(item)}
            onReplaceImage={(item, file) => replaceImage.mutate({ item, file })}
            onCropImage={(item) => setCropTarget(item)}
            onAddSceneFromImage={(item) => addScene.mutate(item.id)}
            onApplyTemplate={(key) => applyTemplate.mutate(key)}
            onUpdateAudio={(changes) => updateAudio.mutate(changes)}
            onUpdateProject={(changes) => updateProject.mutate(changes)}
            onGeneratePlan={(payload) => generatePlan.mutate(payload)}
            onDraftVoiceScript={() => draftVoiceScript.mutate()}
            onGenerateVoiceOver={() => generateVoiceOver.mutate()}
            onUpdateVoiceOver={(changes) => updateVoiceOver.mutate(changes)}
          />
        </aside>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 items-center justify-center bg-canvas p-4">
            <PreviewStage
              className="h-full w-full max-w-[420px]"
              scenes={scenes}
              format={data.format}
              audio={data.audio}
              voiceOver={data.voice_over}
            />
          </div>

          <Timeline
            scenes={scenes}
            audio={data.audio}
            voiceOver={data.voice_over}
            busy={reorderScenes.isPending || duplicateScene.isPending}
            onReorder={(ids) => reorderScenes.mutate(ids)}
            onDuplicate={(scene) => duplicateScene.mutate(scene)}
            onDelete={(scene) => setPendingSceneDelete(scene)}
            onAddScene={() => addScene.mutate(images[0]?.id ?? null)}
          />
        </div>

        <aside
          className={cn(
            "shrink-0 border-l border-line bg-surface transition-[width]",
            rightOpen ? "w-full lg:w-[320px]" : "hidden",
          )}
        >
          <SceneProperties
            scene={selectedScene}
            sceneIndex={selectedIndex}
            isFirst={selectedIndex === 0}
            images={images}
            options={options.data}
            capabilities={capabilities.data}
            saving={updateScene.isPending}
            onChange={(changes) =>
              selectedScene && updateScene.mutate({ sceneId: selectedScene.id, changes })
            }
            onGenerateAiMotion={(prompt) =>
              selectedScene && generateAiMotion.mutate({ sceneId: selectedScene.id, prompt })
            }
          />
        </aside>
      </div>

      {/* ----------------------------------------------------------- dialogs */}
      <RenderDialog
        open={renderOpen}
        jobId={renderJobId}
        projectName={data.name}
        onClose={() => setRenderOpen(false)}
        onCompleted={() => void refresh()}
      />

      <CropModal
        key={cropTarget?.id ?? "no-crop"}
        open={cropTarget !== null}
        media={cropTarget}
        format={data.format}
        saving={cropImage.isPending}
        onClose={() => setCropTarget(null)}
        onApply={(rect) => cropTarget && cropImage.mutate({ item: cropTarget, rect })}
      />

      <ConfirmDialog
        open={pendingSceneDelete !== null}
        onClose={() => setPendingSceneDelete(null)}
        onConfirm={() => pendingSceneDelete && deleteScene.mutate(pendingSceneDelete)}
        title="Delete this scene?"
        message="The scene, its text and its timing will be removed. The image stays in your media library."
        confirmLabel="Delete scene"
        destructive
        loading={deleteScene.isPending}
      />
    </div>
  );
}
