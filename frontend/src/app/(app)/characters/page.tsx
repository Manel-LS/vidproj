"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Users } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState, Notice, Spinner } from "@/components/ui/Feedback";
import { ConfirmDialog } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { CharacterCard, CharacterForm } from "@/components/characters/CharacterForm";
import { api } from "@/lib/api/client";
import type { Character, CharacterDraft } from "@/lib/api/types";

/**
 * Character Studio.
 *
 * A character is the one thing in this product that crosses projects: its frozen
 * description and its reference image are what keep the same face turning up in
 * video after video. The CRUD existed server-side from the start; this is the
 * first client for it.
 */
export default function CharactersPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [editing, setEditing] = useState<Character | null>(null);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Character | null>(null);

  const characters = useQuery({ queryKey: ["characters"], queryFn: api.listCharacters });
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["characters"] });

  const create = useMutation({
    mutationFn: (draft: CharacterDraft) => api.createCharacter(draft),
    onSuccess: (created) => {
      toast.success(`${created.name} saved`);
      setCreating(false);
      setEditing(created);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const update = useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: Partial<CharacterDraft> }) =>
      api.updateCharacter(id, draft),
    onSuccess: (saved) => {
      toast.success("Character updated");
      setEditing(saved);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const remove = useMutation({
    mutationFn: (character: Character) => api.deleteCharacter(character.id),
    onSuccess: () => {
      toast.success("Character deleted", "Projects that used it keep working.");
      setPendingDelete(null);
      setEditing(null);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const uploadReference = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) =>
      api.uploadCharacterReference(id, file),
    onSuccess: (saved) => {
      toast.success("Reference image saved");
      setEditing(saved);
      void refresh();
    },
    onError: (error) => toast.fromError(error),
  });

  const items = characters.data ?? [];
  const imageAi = capabilities.data?.image;

  return (
    <div className="mx-auto max-w-[1100px] px-5 py-8 lg:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Characters</h1>
          <p className="mt-1 text-sm text-muted">
            Save a person once and every video can reuse the same face.
          </p>
        </div>
        <Button
          icon={<Plus className="h-4 w-4" />}
          onClick={() => {
            setEditing(null);
            setCreating(true);
          }}
        >
          New character
        </Button>
      </header>

      {imageAi && !imageAi.available ? (
        <Notice tone="info" className="mb-5">
          {imageAi.message} Characters are still worth saving — they are applied as soon as an
          image provider is configured.
        </Notice>
      ) : null}

      {characters.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner label="Loading your characters…" />
        </div>
      ) : characters.isError ? (
        <Notice tone="danger">
          {characters.error instanceof Error
            ? characters.error.message
            : "Could not load your characters."}
        </Notice>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
          <div className="space-y-2.5">
            {items.length === 0 && !creating ? (
              <EmptyState
                icon={<Users className="h-6 w-6" />}
                title="No characters yet"
                description="Describe someone once — their age, clothes, the way they look — and every generated image keeps them recognisable."
                action={<Button onClick={() => setCreating(true)}>Create one</Button>}
              />
            ) : (
              items.map((character) => (
                <CharacterCard
                  key={character.id}
                  character={character}
                  selected={editing?.id === character.id}
                  onSelect={() => {
                    setCreating(false);
                    setEditing(character);
                  }}
                  onDelete={() => setPendingDelete(character)}
                />
              ))
            )}
          </div>

          <div>
            {creating || editing ? (
              <div className="rounded-panel border border-line bg-surface p-5">
                <h2 className="mb-4 text-sm font-semibold text-ink">
                  {editing ? editing.name : "New character"}
                </h2>
                <CharacterForm
                  // Remount when the selection changes, so the fields re-seed.
                  key={editing?.id ?? "new"}
                  character={editing}
                  saving={create.isPending || update.isPending}
                  uploading={uploadReference.isPending}
                  onSave={(draft) =>
                    editing
                      ? update.mutate({ id: editing.id, draft })
                      : create.mutate(draft)
                  }
                  onUploadReference={(file) =>
                    editing && uploadReference.mutate({ id: editing.id, file })
                  }
                  onCancel={() => {
                    setCreating(false);
                    setEditing(null);
                  }}
                />
              </div>
            ) : items.length ? (
              <div className="rounded-panel border border-dashed border-line px-6 py-14 text-center text-sm text-muted">
                Pick a character to edit it.
              </div>
            ) : null}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "this character"}?`}
        message="Projects that used it keep working — each scene already holds its own prompt. The reference image stays in your media."
        confirmLabel="Delete character"
        destructive
        loading={remove.isPending}
      />
    </div>
  );
}
