"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Palette, Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState, Notice, Spinner } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { BrandKitCard, BrandKitForm } from "@/components/brand/BrandKitForm";
import { api } from "@/lib/api/client";
import type { BrandKit, BrandKitDraft } from "@/lib/api/types";

/**
 * Brand kits.
 *
 * The constants a brand keeps between videos: name, slogan, three colours and a
 * logo. A project points at one, and the kit is copied onto the plan at render
 * time — so editing a kit changes the next video, never a video already made.
 */
export default function BrandPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [editing, setEditing] = useState<BrandKit | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<BrandKit | null>(null);

  const kits = useQuery({ queryKey: ["brand-kits"], queryFn: api.listBrandKits });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["brand-kits"] });

  const create = useMutation({
    mutationFn: (draft: BrandKitDraft) => api.createBrandKit(draft),
    onSuccess: (saved) => {
      toast.success(`${saved.name} saved`);
      setCreating(false);
      setEditing(saved);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const update = useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: Partial<BrandKitDraft> }) =>
      api.updateBrandKit(id, draft),
    onSuccess: (saved) => {
      toast.success("Brand kit updated");
      setEditing(saved);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const remove = useMutation({
    mutationFn: (kit: BrandKit) => api.deleteBrandKit(kit.id),
    onSuccess: () => {
      toast.success("Brand kit deleted", "Projects that used it keep working.");
      setPendingDelete(null);
      setEditing(null);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const uploadLogo = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => api.uploadBrandLogo(id, file),
    onSuccess: (saved) => {
      toast.success("Logo saved");
      setEditing(saved);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const items = kits.data ?? [];

  return (
    <div className="mx-auto max-w-[1100px] px-5 py-8 lg:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Brand</h1>
          <p className="mt-1 text-sm text-muted">
            Set your colours and logo once; every video made with the kit carries them.
          </p>
        </div>
        <Button
          icon={<Plus className="h-4 w-4" />}
          onClick={() => {
            setEditing(null);
            setCreating(true);
          }}
        >
          New brand kit
        </Button>
      </header>

      {kits.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner label="Loading your brand kits…" />
        </div>
      ) : kits.isError ? (
        <Notice tone="danger">
          {kits.error instanceof Error ? kits.error.message : "Could not load your brand kits."}
        </Notice>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
          <div className="space-y-2.5">
            {items.length === 0 && !creating ? (
              <EmptyState
                icon={<Palette className="h-6 w-6" />}
                title="No brand kit yet"
                description="A logo, three colours and a slogan — applied automatically to every video you render."
                action={<Button onClick={() => setCreating(true)}>Create one</Button>}
              />
            ) : (
              items.map((kit) => (
                <BrandKitCard
                  key={kit.id}
                  kit={kit}
                  selected={editing?.id === kit.id}
                  onSelect={() => {
                    setCreating(false);
                    setEditing(kit);
                  }}
                  onDelete={() => setPendingDelete(kit)}
                />
              ))
            )}
          </div>

          <div>
            {creating || editing ? (
              <div className="rounded-panel border border-line bg-surface p-5">
                <h2 className="mb-4 text-sm font-semibold text-ink">
                  {editing ? editing.name : "New brand kit"}
                </h2>
                <BrandKitForm
                  // Remount on selection so the fields re-seed from the chosen kit.
                  key={editing?.id ?? "new"}
                  kit={editing}
                  saving={create.isPending || update.isPending}
                  uploading={uploadLogo.isPending}
                  onSave={(draft) =>
                    editing ? update.mutate({ id: editing.id, draft }) : create.mutate(draft)
                  }
                  onUploadLogo={(file) => editing && uploadLogo.mutate({ id: editing.id, file })}
                  onCancel={() => {
                    setCreating(false);
                    setEditing(null);
                  }}
                />
              </div>
            ) : items.length ? (
              <div className="rounded-panel border border-dashed border-line px-6 py-14 text-center text-sm text-muted">
                Pick a brand kit to edit it.
              </div>
            ) : null}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "this brand kit"}?`}
        message="Projects that used it keep working — a rendered video already carries the colours it was made with. The logo stays in your media."
        confirmLabel="Delete brand kit"
        destructive
        loading={remove.isPending}
      />
    </div>
  );
}
