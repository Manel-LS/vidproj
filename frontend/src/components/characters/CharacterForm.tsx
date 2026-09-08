"use client";

import { useRef, useState } from "react";
import { ImagePlus, Trash2, User } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import type { Character, CharacterDraft, CharacterKind } from "@/lib/api/types";

const KINDS: Array<{ value: CharacterKind; label: string }> = [
  { value: "baby", label: "Baby / toddler" },
  { value: "child", label: "Child" },
  { value: "teen", label: "Teenager" },
  { value: "adult", label: "Adult" },
  { value: "elder", label: "Elderly person" },
  { value: "fictional", label: "Fictional character" },
  { value: "animal", label: "Animal" },
];

const EMPTY: CharacterDraft = {
  name: "",
  kind: "adult",
  age: "",
  gender: "",
  skin_tone: "",
  hair: "",
  clothes: "",
  headwear: "",
  expression: "",
  personality: "",
  environment: "",
  description: "",
};

/**
 * Editing one character.
 *
 * The description is the part that matters: it is composed once from these fields
 * and then replayed verbatim into every image prompt. So the form shows it, and a
 * description typed by hand is kept as written — the server treats a supplied one
 * as authoritative over anything it would assemble from the dropdowns.
 */
export function CharacterForm({
  character,
  saving,
  uploading,
  onSave,
  onUploadReference,
  onCancel,
}: {
  character: Character | null;
  saving?: boolean;
  uploading?: boolean;
  onSave: (draft: CharacterDraft) => void;
  onUploadReference?: (file: File) => void;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<CharacterDraft>(
    character ? { ...(character as unknown as CharacterDraft) } : { ...EMPTY },
  );
  const fileInput = useRef<HTMLInputElement>(null);

  function set<K extends keyof CharacterDraft>(key: K, value: CharacterDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  const named = Boolean(draft.name?.trim());

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (named) onSave(draft);
      }}
    >
      <div className="flex items-start gap-4">
        <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl border border-line bg-elevated">
          {character?.reference_image_url ? (
            <img
              src={character.reference_image_url}
              alt={`Reference for ${character.name}`}
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="flex h-full w-full items-center justify-center text-faint">
              <User className="h-7 w-7" aria-hidden />
            </span>
          )}
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <Input
            label="Name"
            value={draft.name ?? ""}
            onChange={(event) => set("name", event.target.value)}
            placeholder="Skander"
            maxLength={120}
            required
          />
          {character ? (
            <>
              <input
                ref={fileInput}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onUploadReference?.(file);
                  event.target.value = "";
                }}
              />
              <Button
                type="button"
                size="sm"
                variant="secondary"
                loading={uploading}
                icon={<ImagePlus className="h-3.5 w-3.5" />}
                onClick={() => fileInput.current?.click()}
              >
                {character.reference_image_url ? "Replace reference" : "Add reference image"}
              </Button>
            </>
          ) : (
            <p className="text-xs text-faint">
              Save the character first, then add a reference image.
            </p>
          )}
        </div>
      </div>

      <Select
        label="What are they?"
        value={draft.kind ?? "adult"}
        options={KINDS}
        onChange={(event) => set("kind", event.target.value as CharacterKind)}
      />

      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Age"
          value={draft.age ?? ""}
          onChange={(event) => set("age", event.target.value)}
          placeholder="2 years old"
          maxLength={60}
        />
        <Input
          label="Gender"
          value={draft.gender ?? ""}
          onChange={(event) => set("gender", event.target.value)}
          placeholder="boy"
          maxLength={40}
        />
        <Input
          label="Skin tone"
          value={draft.skin_tone ?? ""}
          onChange={(event) => set("skin_tone", event.target.value)}
          placeholder="olive skin"
          maxLength={60}
        />
        <Input
          label="Hair"
          value={draft.hair ?? ""}
          onChange={(event) => set("hair", event.target.value)}
          placeholder="short curly black hair"
          maxLength={120}
        />
        <Input
          label="Headwear"
          value={draft.headwear ?? ""}
          onChange={(event) => set("headwear", event.target.value)}
          placeholder="a red chechia"
          maxLength={160}
        />
        <Input
          label="Expression"
          value={draft.expression ?? ""}
          onChange={(event) => set("expression", event.target.value)}
          placeholder="a wide mischievous smile"
          maxLength={120}
        />
      </div>

      <Input
        label="Clothes"
        value={draft.clothes ?? ""}
        onChange={(event) => set("clothes", event.target.value)}
        placeholder="a red velvet jebba with gold trim"
        maxLength={300}
      />

      <Input
        label="Usual surroundings"
        value={draft.environment ?? ""}
        onChange={(event) => set("environment", event.target.value)}
        placeholder="a sunlit Tunisian courtyard"
        maxLength={300}
      />

      <Input
        label="Personality"
        value={draft.personality ?? ""}
        onChange={(event) => set("personality", event.target.value)}
        placeholder="cheeky, talkative, always negotiating"
        maxLength={200}
        hint="Used for the writing, not the drawing."
      />

      <Textarea
        label="Description"
        value={draft.description ?? ""}
        onChange={(event) => set("description", event.target.value)}
        placeholder="Leave empty to have it written from the fields above."
        maxLength={1200}
        className="min-h-[80px]"
        hint="This exact sentence goes into every image prompt. Write your own to override it; clear it to have it rebuilt."
      />

      {character?.description ? (
        <Notice tone="info" title="Currently sent to the image provider">
          <span className="italic">the same {character.description}</span>
        </Notice>
      ) : null}

      <div className="flex justify-end gap-2">
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
        <Button type="submit" loading={saving} disabled={!named}>
          {character ? "Save changes" : "Create character"}
        </Button>
      </div>
    </form>
  );
}

export function CharacterCard({
  character,
  selected,
  onSelect,
  onDelete,
}: {
  character: Character;
  selected?: boolean;
  onSelect: () => void;
  onDelete?: () => void;
}) {
  return (
    <article
      className={
        selected
          ? "flex items-center gap-3 rounded-card border border-accent bg-accent/5 p-3"
          : "flex items-center gap-3 rounded-card border border-line bg-surface p-3 transition-colors hover:border-accent/40"
      }
    >
      <button type="button" onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-3 text-left">
        <span className="h-11 w-11 shrink-0 overflow-hidden rounded-lg bg-elevated">
          {character.reference_image_url ? (
            <img src={character.reference_image_url} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="flex h-full w-full items-center justify-center text-faint">
              <User className="h-5 w-5" aria-hidden />
            </span>
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">{character.name}</span>
          <span className="block truncate text-xs text-muted">
            {character.description || "No description yet"}
          </span>
        </span>
      </button>
      {onDelete ? (
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Delete ${character.name}`}
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      ) : null}
    </article>
  );
}
