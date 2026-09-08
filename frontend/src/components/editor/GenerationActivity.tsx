"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clapperboard,
  Film,
  Image as ImageIcon,
  Loader2,
  Mic,
  PenLine,
  Smile,
} from "lucide-react";
import type { ReactNode } from "react";
import { Badge, Notice, ProgressBar } from "@/components/ui/Feedback";
import { api } from "@/lib/api/client";
import type { GenerationJob, GenerationJobType, RenderStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * What this project is doing, across every kind of generation (requirement 17).
 *
 * The backend already records image, motion, voice, lip-sync and render work in one
 * registry; this reads it in a single poll. Deliberately *not* a fixed checklist of
 * invented stages: a step appears only once a job of that kind actually exists, so
 * the strip never shows progress through work the deployment cannot perform.
 */

const STEPS: { type: GenerationJobType; label: string; icon: ReactNode }[] = [
  { type: "story", label: "Script", icon: <PenLine className="h-3.5 w-3.5" aria-hidden /> },
  { type: "image", label: "Images", icon: <ImageIcon className="h-3.5 w-3.5" aria-hidden /> },
  { type: "video", label: "Motion", icon: <Clapperboard className="h-3.5 w-3.5" aria-hidden /> },
  { type: "voice", label: "Voice-over", icon: <Mic className="h-3.5 w-3.5" aria-hidden /> },
  { type: "lipsync", label: "Lip sync", icon: <Smile className="h-3.5 w-3.5" aria-hidden /> },
  { type: "render", label: "Video", icon: <Film className="h-3.5 w-3.5" aria-hidden /> },
];

const ACTIVE: RenderStatus[] = ["queued", "processing"];

/** The worst outcome across the jobs of one kind — a single failure must not hide behind four successes. */
function stepStatus(jobs: GenerationJob[]): RenderStatus | "idle" {
  if (!jobs.length) return "idle";
  if (jobs.some((job) => ACTIVE.includes(job.status))) return "processing";
  if (jobs.some((job) => job.status === "failed")) return "failed";
  if (jobs.some((job) => job.status === "completed")) return "completed";
  return jobs[0].status;
}

function StepPill({
  label,
  icon,
  status,
  count,
}: {
  label: string;
  icon: ReactNode;
  status: RenderStatus | "idle";
  count: number;
}) {
  const running = status === "processing";
  return (
    <li
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-2xs font-medium transition-colors",
        status === "idle" && "border-line bg-elevated text-faint",
        running && "border-accent/30 bg-accent/10 text-accent",
        status === "completed" && "border-positive/25 bg-positive/10 text-positive",
        status === "failed" && "border-danger/30 bg-danger/10 text-danger",
        status === "cancelled" && "border-line bg-elevated text-muted",
      )}
      aria-current={running ? "step" : undefined}
    >
      {running ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      ) : status === "completed" ? (
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
      ) : status === "failed" ? (
        <AlertCircle className="h-3.5 w-3.5" aria-hidden />
      ) : (
        icon
      )}
      {label}
      {count > 1 ? <span className="opacity-70">×{count}</span> : null}
      <span className="sr-only">
        {status === "idle" ? "not started" : running ? "in progress" : status}
      </span>
    </li>
  );
}

export function GenerationActivity({
  projectId,
  className,
}: {
  projectId: string;
  className?: string;
}) {
  const jobs = useQuery({
    queryKey: ["project-jobs", projectId],
    queryFn: () => api.projectJobs(projectId, { limit: 60 }),
    // Poll only while something is running; an idle project costs one request.
    refetchInterval: (query) => (query.state.data?.active ? 1500 : false),
  });

  const data = jobs.data;
  // The registry is an aid, not a dependency: if reading it fails the editor is
  // still perfectly usable, so this stays silent rather than showing an error.
  if (!data || data.total === 0) return null;

  const byType = new Map<GenerationJobType, GenerationJob[]>();
  for (const job of data.items) {
    const list = byType.get(job.type);
    if (list) list.push(job);
    else byType.set(job.type, [job]);
  }

  const running = data.items.find((job) => ACTIVE.includes(job.status));
  const failed = !running ? data.items.find((job) => job.status === "failed") : undefined;
  const visible = STEPS.filter((step) => byType.has(step.type));
  if (!visible.length) return null;

  return (
    <section
      className={cn("rounded-xl border border-line bg-surface px-3 py-2.5", className)}
      aria-label="Generation activity"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <ol className="flex flex-wrap items-center gap-1.5">
          {visible.map((step) => {
            const list = byType.get(step.type) ?? [];
            return (
              <StepPill
                key={step.type}
                label={step.label}
                icon={step.icon}
                status={stepStatus(list)}
                count={list.length}
              />
            );
          })}
        </ol>

        <div className="ml-auto flex items-center gap-2">
          {running ? (
            <>
              <span className="text-2xs text-muted">{running.stage || "Working…"}</span>
              <span className="font-mono text-2xs tabular-nums text-faint">{data.progress}%</span>
            </>
          ) : failed ? (
            <Badge tone="danger">Needs attention</Badge>
          ) : (
            <Badge tone="success">Up to date</Badge>
          )}
        </div>
      </div>

      {running ? <ProgressBar value={data.progress} className="mt-2.5" /> : null}

      {failed?.error ? (
        <Notice tone="danger" className="mt-2.5">
          {failed.error}
        </Notice>
      ) : null}
    </section>
  );
}
