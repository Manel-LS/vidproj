"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { EmptyState, Notice, Spinner } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ProjectCard } from "@/components/projects/ProjectCard";
import { api } from "@/lib/api/client";
import type { ProjectSummary } from "@/lib/api/types";

export default function DashboardPage() {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ProjectSummary | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const projects = useQuery({
    queryKey: ["projects", search],
    queryFn: () => api.listProjects({ limit: 48, search }),
    // While something is rendering, keep the cards' progress moving.
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (item) => item.render_status === "processing" || item.render_status === "queued",
      )
        ? 2500
        : false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["projects"] });

  const duplicate = useMutation({
    mutationFn: (project: ProjectSummary) => api.duplicateProject(project.id),
    onMutate: (project) => setBusyId(project.id),
    onSuccess: (copy) => {
      toast.success("Project duplicated", `“${copy.name}” is ready to edit.`);
      void invalidate();
    },
    onError: (error) => toast.fromError(error),
    onSettled: () => setBusyId(null),
  });

  const remove = useMutation({
    mutationFn: (project: ProjectSummary) => api.deleteProject(project.id),
    onSuccess: () => {
      toast.success("Project deleted");
      setPendingDelete(null);
      void invalidate();
    },
    onError: (error) => toast.fromError(error),
  });

  const render = useMutation({
    mutationFn: (project: ProjectSummary) => api.startRender(project.id),
    onMutate: (project) => setBusyId(project.id),
    onSuccess: (job) => {
      toast.info("Your video is being generated…", "You can keep working while it renders.");
      void invalidate();
      router.push(`/editor/${job.project_id}?job=${job.id}`);
    },
    onError: (error) => toast.fromError(error),
    onSettled: () => setBusyId(null),
  });

  const items = useMemo(() => projects.data?.items ?? [], [projects.data]);
  const total = projects.data?.total ?? 0;

  const stats = useMemo(() => {
    const rendered = items.filter((item) => item.render_status === "completed").length;
    const seconds = items.reduce((sum, item) => sum + item.duration_seconds, 0);
    return { rendered, seconds };
  }, [items]);

  return (
    <div className="mx-auto max-w-[1400px] px-5 py-8 lg:px-8">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted">
            {total === 0
              ? "Nothing here yet — your first video is a few clicks away."
              : `${total} project${total === 1 ? "" : "s"} · ${stats.rendered} rendered · ${Math.round(stats.seconds)}s of video`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" aria-hidden />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search projects"
              className="w-56 pl-9"
              aria-label="Search projects"
            />
          </div>
          <Button icon={<Plus className="h-4 w-4" />} onClick={() => router.push("/create")}>
            Create Video
          </Button>
        </div>
      </header>

      {projects.isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="skeleton aspect-[9/16] rounded-card" />
          ))}
        </div>
      ) : projects.isError ? (
        <Notice
          tone="danger"
          title="Could not load your projects"
          action={
            <Button size="sm" variant="secondary" onClick={() => projects.refetch()}>
              Retry
            </Button>
          }
        >
          {projects.error instanceof Error ? projects.error.message : "Please try again."}
        </Notice>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<FolderOpen className="h-6 w-6" />}
          title={search ? "No projects match that search" : "Create your first video"}
          description={
            search
              ? "Try a different name, or clear the search."
              : "Upload a few product photos and Reelcraft will plan the scenes, animate them and render an MP4 ready for TikTok, Reels and Shorts."
          }
          action={
            search ? (
              <Button variant="secondary" onClick={() => setSearch("")}>
                Clear search
              </Button>
            ) : (
              <Button icon={<Plus className="h-4 w-4" />} onClick={() => router.push("/create")}>
                Create Video
              </Button>
            )
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {items.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              busy={busyId === project.id}
              onDuplicate={(target) => duplicate.mutate(target)}
              onDelete={(target) => setPendingDelete(target)}
              onRender={(target) => render.mutate(target)}
            />
          ))}
        </div>
      )}

      {items.length > 0 ? (
        <p className="mt-8 text-center text-xs text-faint">
          Need a starting point?{" "}
          <Link href="/templates" className="text-accent hover:underline">
            Browse templates
          </Link>
        </p>
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete)}
        title="Delete this project?"
        message={`“${pendingDelete?.name}” and everything in it — images, audio and rendered videos — will be permanently removed. This cannot be undone.`}
        confirmLabel="Delete project"
        destructive
        loading={remove.isPending}
      />

      {projects.isFetching && !projects.isLoading ? (
        <div className="pointer-events-none fixed bottom-4 left-1/2 -translate-x-1/2">
          <Spinner />
        </div>
      ) : null}
    </div>
  );
}
