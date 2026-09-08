"use client";

import { useMemo, useRef } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToHorizontalAxis, restrictToParentElement } from "@dnd-kit/modifiers";
import {
  SortableContext,
  arrayMove,
  horizontalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Copy, GripHorizontal, ImageOff, Music, Plus, Trash2, Type } from "lucide-react";
import type { AudioTrack, Scene, VoiceOver } from "@/lib/api/types";
import { buildTimeline, formatTime } from "@/lib/video/timeline";
import { useEditorStore } from "@/lib/store/editor";
import { cn, humanise } from "@/lib/utils";

/**
 * The timeline: an image track, a text track and an audio track.
 *
 * Deliberately not a professional NLE — scenes are cards you can drag, not clips on
 * a pixel-accurate ruler. Duration is edited numerically in the properties panel,
 * which is both easier to hit and easier to get exactly right.
 */
export function Timeline({
  scenes,
  audio,
  voiceOver,
  onReorder,
  onDuplicate,
  onDelete,
  onAddScene,
  busy,
}: {
  scenes: Scene[];
  audio: AudioTrack | null;
  voiceOver: VoiceOver | null;
  onReorder: (sceneIds: string[]) => void;
  onDuplicate: (scene: Scene) => void;
  onDelete: (scene: Scene) => void;
  onAddScene: () => void;
  busy?: boolean;
}) {
  const { selectedSceneId, select, time, setTime } = useEditorStore();
  const trackRef = useRef<HTMLDivElement>(null);

  const timeline = useMemo(() => buildTimeline(scenes), [scenes]);
  const duration = timeline.length ? Math.max(...timeline.map((item) => item.end)) : 0;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = timeline.map((item) => item.scene.id);
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    onReorder(arrayMove(ids, from, to));
  }

  const playheadPercent = duration > 0 ? (time / duration) * 100 : 0;

  return (
    <section className="flex flex-col border-t border-line bg-surface" aria-label="Timeline">
      {/* Ruler */}
      <div
        className="relative h-6 cursor-pointer border-b border-line px-3"
        ref={trackRef}
        onClick={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - bounds.left) / bounds.width;
          setTime(Math.max(0, Math.min(duration, ratio * duration)));
        }}
        role="slider"
        aria-label="Timeline ruler"
        aria-valuemin={0}
        aria-valuemax={duration}
        aria-valuenow={time}
        tabIndex={0}
      >
        <div className="flex h-full items-center justify-between text-2xs text-faint">
          <span>0:00</span>
          <span>{formatTime(duration / 2)}</span>
          <span>{formatTime(duration)}</span>
        </div>
        <span
          className="pointer-events-none absolute top-0 h-full w-px bg-accent"
          style={{ left: `calc(${playheadPercent}% )` }}
          aria-hidden
        />
      </div>

      <div className="max-h-[42vh] overflow-y-auto px-3 py-3">
        {/* Image track */}
        <TrackLabel icon={<ImageOff className="h-3 w-3" />} label="Scenes" count={scenes.length} />
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          modifiers={[restrictToHorizontalAxis, restrictToParentElement]}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={timeline.map((item) => item.scene.id)}
            strategy={horizontalListSortingStrategy}
          >
            <div className="flex items-stretch gap-2 overflow-x-auto pb-2">
              {timeline.map((item, index) => (
                <SceneCard
                  key={item.scene.id}
                  scene={item.scene}
                  index={index}
                  start={item.start}
                  selected={selectedSceneId === item.scene.id}
                  onSelect={() => {
                    select(item.scene.id);
                    setTime(item.start + 0.01);
                  }}
                  onDuplicate={() => onDuplicate(item.scene)}
                  onDelete={() => onDelete(item.scene)}
                  disabled={busy}
                  canDelete={scenes.length > 1}
                />
              ))}

              <button
                type="button"
                onClick={onAddScene}
                disabled={busy}
                className="flex h-[68px] w-14 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line text-faint transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-40"
                aria-label="Add a scene"
              >
                <Plus className="h-4 w-4" aria-hidden />
                <span className="text-2xs">Scene</span>
              </button>
            </div>
          </SortableContext>
        </DndContext>

        {/* Text track */}
        <TrackLabel
          icon={<Type className="h-3 w-3" />}
          label="Text"
          count={scenes.reduce((sum, scene) => sum + scene.texts.length, 0)}
        />
        <div className="mb-3 flex gap-2 overflow-x-auto">
          {timeline.map((item) => (
            <div
              key={item.scene.id}
              className={cn(
                "flex h-7 w-24 shrink-0 items-center rounded-md border px-2 text-2xs",
                item.scene.texts.length
                  ? "border-accent/30 bg-accent/10 text-accent"
                  : "border-line bg-elevated/50 text-faint",
              )}
              title={item.scene.texts.map((text) => text.content).join(" · ")}
            >
              <span className="truncate">
                {item.scene.texts[0]?.content ?? "No text"}
              </span>
            </div>
          ))}
        </div>

        {/* Audio track */}
        <TrackLabel icon={<Music className="h-3 w-3" />} label="Audio" />
        <div className="flex gap-2">
          <div
            className={cn(
              "flex h-7 flex-1 items-center gap-2 rounded-md border px-2.5 text-2xs",
              audio?.media
                ? "border-positive/30 bg-positive/10 text-positive"
                : "border-line bg-elevated/50 text-faint",
            )}
          >
            <Music className="h-3 w-3 shrink-0" aria-hidden />
            <span className="truncate">
              {audio?.media
                ? `${audio.media.original_filename} · ${Math.round(audio.volume * 100)}%`
                : "No music — add a track in the Audio panel"}
            </span>
          </div>
          {voiceOver?.enabled ? (
            <div
              className={cn(
                "flex h-7 w-48 items-center gap-2 rounded-md border px-2.5 text-2xs",
                voiceOver.media
                  ? "border-accent/30 bg-accent/10 text-accent"
                  : "border-warning/30 bg-warning/10 text-warning",
              )}
            >
              <span className="truncate">
                {voiceOver.media ? "Voice-over ready" : "Voice-over script only"}
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function TrackLabel({
  icon,
  label,
  count,
}: {
  icon: React.ReactNode;
  label: string;
  count?: number;
}) {
  return (
    <div className="mb-1.5 flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wider text-faint">
      {icon}
      {label}
      {count !== undefined ? <span className="text-faint/70">({count})</span> : null}
    </div>
  );
}

function SceneCard({
  scene,
  index,
  start,
  selected,
  onSelect,
  onDuplicate,
  onDelete,
  disabled,
  canDelete,
}: {
  scene: Scene;
  index: number;
  start: number;
  selected: boolean;
  onSelect: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  disabled?: boolean;
  canDelete: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: scene.id,
    disabled,
  });

  // Wider cards for longer scenes, so the timeline reads as a timeline.
  const width = Math.max(56, Math.min(140, 34 + scene.duration * 16));

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, width }}
      className={cn(
        "group relative h-[68px] shrink-0 overflow-hidden rounded-lg border transition-colors",
        selected ? "border-accent ring-2 ring-accent/25" : "border-line hover:border-accent/40",
        isDragging && "z-10 opacity-80",
      )}
    >
      <button type="button" onClick={onSelect} className="block h-full w-full text-left">
        {scene.media?.thumbnail_url || scene.media?.url ? (
          <img
            src={scene.media.thumbnail_url ?? scene.media.url}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            draggable={false}
          />
        ) : (
          <span className="checkerboard flex h-full w-full items-center justify-center">
            <ImageOff className="h-4 w-4 text-faint" aria-hidden />
          </span>
        )}

        <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-1.5 pb-1 pt-4">
          <span className="block truncate text-2xs font-medium text-white">
            {index + 1}. {humanise(scene.animation)}
          </span>
          <span className="block text-2xs text-white/65">
            {scene.duration.toFixed(1)}s · {formatTime(start)}
          </span>
        </span>
      </button>

      <span className="absolute right-1 top-1 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          {...attributes}
          {...listeners}
          className="cursor-grab rounded bg-black/70 p-0.5 text-white/80 active:cursor-grabbing"
          aria-label={`Reorder scene ${index + 1}`}
        >
          <GripHorizontal className="h-3 w-3" aria-hidden />
        </button>
        <button
          type="button"
          onClick={onDuplicate}
          className="rounded bg-black/70 p-0.5 text-white/80 hover:bg-black"
          aria-label={`Duplicate scene ${index + 1}`}
        >
          <Copy className="h-3 w-3" aria-hidden />
        </button>
        {canDelete ? (
          <button
            type="button"
            onClick={onDelete}
            className="rounded bg-danger/75 p-0.5 text-white hover:bg-danger"
            aria-label={`Delete scene ${index + 1}`}
          >
            <Trash2 className="h-3 w-3" aria-hidden />
          </button>
        ) : null}
      </span>

      {scene.transition !== "none" && index > 0 ? (
        // Inside the card: the card clips its overflow, so a chip straddling the left
        // edge would be sliced in half and read as stray letters.
        <span
          className="pointer-events-none absolute left-1 top-1 max-w-[calc(100%-2.5rem)] truncate rounded bg-black/75 px-1 py-px text-[9px] text-white/80 backdrop-blur"
          title={`Transition in: ${humanise(scene.transition)} · ${scene.transition_duration.toFixed(2)}s`}
        >
          {humanise(scene.transition)}
        </span>
      ) : null}
    </div>
  );
}
