"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Film, Images, Music } from "lucide-react";
import { Badge, EmptyState, Spinner } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api/client";
import type { MediaItem } from "@/lib/api/types";
import { cn, formatBytes, formatRelativeDate } from "@/lib/utils";

type Filter = "all" | "image" | "audio" | "video";

/**
 * Everything the user has uploaded or rendered, across every project.
 *
 * Media belongs to a project on the server, so this view fans out over the user's
 * projects rather than inventing a global media endpoint that would blur ownership.
 */
export default function MediaPage() {
  const [filter, setFilter] = useState<Filter>("all");

  const projects = useQuery({
    queryKey: ["projects", ""],
    queryFn: () => api.listProjects({ limit: 50 }),
  });

  const mediaQueries = useQueries({
    queries: (projects.data?.items ?? []).map((project) => ({
      queryKey: ["media", project.id],
      queryFn: () => api.listMedia(project.id),
      staleTime: 60_000,
    })),
  });

  const rows = useMemo(() => {
    const items = projects.data?.items ?? [];
    const collected: Array<{ media: MediaItem; projectId: string; projectName: string }> = [];
    mediaQueries.forEach((query, index) => {
      const project = items[index];
      if (!project || !query.data) return;
      query.data.forEach((media) => {
        collected.push({ media, projectId: project.id, projectName: project.name });
      });
    });
    return collected
      .filter((row) => filter === "all" || row.media.kind === filter)
      .sort((a, b) => b.media.created_at.localeCompare(a.media.created_at));
  }, [projects.data, mediaQueries, filter]);

  const loading = projects.isLoading || mediaQueries.some((query) => query.isLoading);
  const totalBytes = rows.reduce((sum, row) => sum + row.media.size_bytes, 0);

  const FILTERS: Array<{ key: Filter; label: string; icon: typeof Images }> = [
    { key: "all", label: "Everything", icon: Images },
    { key: "image", label: "Images", icon: Images },
    { key: "audio", label: "Audio", icon: Music },
    { key: "video", label: "Renders", icon: Film },
  ];

  return (
    <div className="mx-auto max-w-[1400px] px-5 py-8 lg:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Media</h1>
          <p className="mt-1 text-sm text-muted">
            {rows.length} file{rows.length === 1 ? "" : "s"} · {formatBytes(totalBytes)}
          </p>
        </div>
        <div className="flex gap-1.5">
          {FILTERS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              onClick={() => setFilter(entry.key)}
              className={cn(
                "rounded-pill border px-3 py-1.5 text-xs transition-colors",
                filter === entry.key
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-line text-muted hover:text-ink",
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </header>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner label="Gathering your files…" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Images className="h-6 w-6" />}
          title="No media yet"
          description="Files you upload to a project — and the videos you render — show up here."
          action={
            <Link href="/create">
              <Button>Create a video</Button>
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6">
          {rows.map(({ media, projectId, projectName }) => (
            <article
              key={media.id}
              className="group overflow-hidden rounded-card border border-line bg-surface"
            >
              <Link href={`/editor/${projectId}`} className="block aspect-square bg-elevated">
                {media.kind === "image" ? (
                  <img
                    src={media.thumbnail_url ?? media.url}
                    alt=""
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : media.kind === "video" ? (
                  <span className="checkerboard flex h-full w-full items-center justify-center">
                    <Film className="h-7 w-7 text-faint" aria-hidden />
                  </span>
                ) : (
                  <span className="checkerboard flex h-full w-full items-center justify-center">
                    <Music className="h-7 w-7 text-faint" aria-hidden />
                  </span>
                )}
              </Link>
              <div className="p-2.5">
                <p className="truncate text-xs text-ink" title={media.original_filename}>
                  {media.original_filename || media.kind}
                </p>
                <p className="mt-0.5 truncate text-2xs text-faint">{projectName}</p>
                <div className="mt-1.5 flex items-center justify-between gap-1">
                  <Badge tone={media.kind === "video" ? "accent" : "neutral"}>{media.kind}</Badge>
                  <span className="text-2xs text-faint">{formatRelativeDate(media.created_at)}</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
