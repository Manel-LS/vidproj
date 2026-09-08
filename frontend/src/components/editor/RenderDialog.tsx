"use client";

import { useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, Film, XCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Notice, ProgressBar } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api/client";
import type { RenderJob } from "@/lib/api/types";
import { downloadBlob } from "@/lib/utils";

const STAGE_STEPS = [0, 25, 50, 75, 100];

/**
 * Render progress (requirement 16).
 *
 * The dialog polls the job while it is queued or processing; the backend is the
 * single source of truth for progress, so a refresh or a second tab shows the same
 * state.
 */
export function RenderDialog({
  open,
  jobId,
  projectName,
  onClose,
  onCompleted,
}: {
  open: boolean;
  jobId: string | null;
  projectName: string;
  onClose: () => void;
  onCompleted?: (job: RenderJob) => void;
}) {
  const toast = useToast();

  const job = useQuery({
    queryKey: ["render-job", jobId],
    queryFn: () => api.getRenderJob(jobId!),
    enabled: Boolean(jobId) && open,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "processing" ? 1200 : false;
    },
  });

  const cancel = useMutation({
    mutationFn: () => api.cancelRenderJob(jobId!),
    onSuccess: () => toast.info("Render cancelled"),
    onError: (error) => toast.fromError(error),
  });

  const download = useMutation({
    mutationFn: async () => {
      const blob = await api.downloadRender(jobId!);
      const safe = projectName.replace(/[^a-z0-9-_]+/gi, "-").toLowerCase() || "video";
      downloadBlob(blob, `${safe}.mp4`);
    },
    onError: (error) => toast.fromError(error),
  });

  const data = job.data;
  const status = data?.status;

  useEffect(() => {
    if (status === "completed" && data) onCompleted?.(data);
  }, [status, data, onCompleted]);

  const active = status === "queued" || status === "processing";
  const progress = data?.progress ?? 0;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        status === "completed"
          ? "Your video is ready."
          : status === "failed"
            ? "Rendering failed"
            : "Your video is being generated…"
      }
      description={
        active
          ? "You can close this and keep editing — the render carries on in the background."
          : undefined
      }
      size="md"
      footer={
        <>
          {active ? (
            <Button variant="ghost" onClick={() => cancel.mutate()} loading={cancel.isPending}>
              Cancel render
            </Button>
          ) : null}
          <Button variant="secondary" onClick={onClose}>
            {active ? "Keep editing" : "Close"}
          </Button>
          {status === "completed" ? (
            <Button
              icon={<Download className="h-4 w-4" />}
              onClick={() => download.mutate()}
              loading={download.isPending}
            >
              Download MP4
            </Button>
          ) : null}
        </>
      }
    >
      {job.isLoading ? (
        <p className="text-sm text-muted">Preparing…</p>
      ) : job.isError ? (
        <Notice tone="danger">
          {job.error instanceof Error ? job.error.message : "Could not read the render status."}
        </Notice>
      ) : data ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <span
              className={
                status === "completed"
                  ? "flex h-10 w-10 items-center justify-center rounded-xl bg-positive/15 text-positive"
                  : status === "failed"
                    ? "flex h-10 w-10 items-center justify-center rounded-xl bg-danger/15 text-danger"
                    : "flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent"
              }
            >
              {status === "completed" ? (
                <CheckCircle2 className="h-5 w-5" aria-hidden />
              ) : status === "failed" ? (
                <XCircle className="h-5 w-5" aria-hidden />
              ) : (
                <Film className="h-5 w-5" aria-hidden />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-ink">{data.message}</p>
              <p className="text-xs text-faint">{data.stage}</p>
            </div>
            <span className="font-mono text-sm tabular-nums text-muted">{progress}%</span>
          </div>

          <ProgressBar value={progress} tone={status === "completed" ? "success" : "accent"} />

          <ol className="flex justify-between text-2xs text-faint">
            {STAGE_STEPS.map((step) => (
              <li key={step} className={progress >= step ? "text-accent" : undefined}>
                {step}%
              </li>
            ))}
          </ol>

          {status === "failed" && data.error ? (
            <Notice tone="danger" title="Video rendering failed. Try again.">
              {data.error}
            </Notice>
          ) : null}

          {status === "completed" && data.output_media ? (
            <video
              controls
              playsInline
              src={data.output_media.url}
              className="mx-auto max-h-[46vh] rounded-xl border border-line bg-black"
            >
              Your browser cannot play this video.
            </video>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}
