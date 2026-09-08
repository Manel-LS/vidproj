"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Clock,
  Copy,
  Download,
  Film,
  Loader2,
  MoreHorizontal,
  Pencil,
  Play,
  Trash2,
} from "lucide-react";
import { Badge, ProgressBar } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import type { ProjectSummary } from "@/lib/api/types";
import { cn, formatDuration, formatRelativeDate } from "@/lib/utils";

const STATUS_TONE = {
  queued: "warning",
  processing: "warning",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
} as const;

const STATUS_LABEL = {
  queued: "Queued",
  processing: "Rendering",
  completed: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
} as const;

export function ProjectCard({
  project,
  onDuplicate,
  onDelete,
  onRender,
  busy,
}: {
  project: ProjectSummary;
  onDuplicate: (project: ProjectSummary) => void;
  onDelete: (project: ProjectSummary) => void;
  onRender: (project: ProjectSummary) => void;
  busy?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const rendering = project.render_status === "processing" || project.render_status === "queued";

  return (
    <article className="group relative flex flex-col overflow-hidden rounded-card border border-line bg-surface transition-colors hover:border-accent/40">
      <Link
        href={`/editor/${project.id}`}
        className="relative block aspect-[9/16] w-full overflow-hidden bg-elevated"
        aria-label={`Open ${project.name}`}
      >
        {project.thumbnail_url ? (
          <img
            src={project.thumbnail_url}
            alt=""
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
            loading="lazy"
          />
        ) : (
          <div className="checkerboard flex h-full w-full items-center justify-center">
            <Film className="h-8 w-8 text-faint" aria-hidden />
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-black/80 to-transparent" />

        <span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-black/60 backdrop-blur">
            <Play className="ml-0.5 h-5 w-5 text-white" aria-hidden />
          </span>
        </span>

        <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
          <Badge>{project.format}</Badge>
          {project.render_status ? (
            <Badge tone={STATUS_TONE[project.render_status]}>
              {rendering ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
              {STATUS_LABEL[project.render_status]}
            </Badge>
          ) : null}
        </div>

        <div className="absolute inset-x-2.5 bottom-2.5 flex items-center gap-2 text-2xs text-white/85">
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" aria-hidden />
            {formatDuration(project.duration_seconds)}
          </span>
          <span aria-hidden>·</span>
          <span>{project.scene_count} scenes</span>
          <span aria-hidden>·</span>
          <span>{project.image_count} images</span>
        </div>
      </Link>

      {rendering ? (
        <ProgressBar value={project.render_progress} className="h-1 rounded-none" />
      ) : null}

      <div className="flex items-start justify-between gap-2 p-3.5">
        <div className="min-w-0">
          <Link href={`/editor/${project.id}`} className="block truncate text-sm font-medium text-ink hover:text-accent">
            {project.name}
          </Link>
          <p className="mt-0.5 truncate text-xs text-faint">
            {formatRelativeDate(project.updated_at)}
          </p>
        </div>

        <div className="relative">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label={`Actions for ${project.name}`}
            aria-expanded={menuOpen}
            disabled={busy}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MoreHorizontal className="h-4 w-4" />}
          </Button>

          {menuOpen ? (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} aria-hidden />
              <div
                className="absolute right-0 top-9 z-20 w-44 animate-scale-in overflow-hidden rounded-xl border border-line bg-elevated py-1 shadow-lifted"
                role="menu"
              >
                <MenuItem href={`/editor/${project.id}`} icon={<Pencil className="h-4 w-4" />} label="Edit" />
                <MenuItem
                  icon={<Film className="h-4 w-4" />}
                  label={rendering ? "Rendering…" : "Render"}
                  disabled={rendering}
                  onClick={() => {
                    setMenuOpen(false);
                    onRender(project);
                  }}
                />
                {project.download_url ? (
                  <MenuItem
                    href={project.download_url}
                    icon={<Download className="h-4 w-4" />}
                    label="Export MP4"
                    download
                  />
                ) : null}
                <MenuItem
                  icon={<Copy className="h-4 w-4" />}
                  label="Duplicate"
                  onClick={() => {
                    setMenuOpen(false);
                    onDuplicate(project);
                  }}
                />
                <div className="my-1 h-px bg-line" />
                <MenuItem
                  icon={<Trash2 className="h-4 w-4" />}
                  label="Delete"
                  destructive
                  onClick={() => {
                    setMenuOpen(false);
                    onDelete(project);
                  }}
                />
              </div>
            </>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  href,
  destructive,
  disabled,
  download,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  href?: string;
  destructive?: boolean;
  disabled?: boolean;
  download?: boolean;
}) {
  const className = cn(
    "flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm transition-colors",
    destructive ? "text-danger hover:bg-danger/10" : "text-muted hover:bg-surface hover:text-ink",
    disabled && "pointer-events-none opacity-40",
  );

  if (href) {
    return (
      <Link href={href} className={className} role="menuitem" download={download} target={download ? "_blank" : undefined}>
        {icon}
        {label}
      </Link>
    );
  }
  return (
    <button type="button" className={className} onClick={onClick} role="menuitem" disabled={disabled}>
      {icon}
      {label}
    </button>
  );
}
