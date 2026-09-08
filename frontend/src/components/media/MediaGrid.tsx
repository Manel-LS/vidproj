"use client";

import { useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToParentElement } from "@dnd-kit/modifiers";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Crop, GripVertical, RefreshCw, Trash2 } from "lucide-react";
import type { MediaItem } from "@/lib/api/types";
import { cn, formatBytes } from "@/lib/utils";

export interface MediaGridProps {
  items: MediaItem[];
  /** Scene number per media id, when the grid is showing a timeline order. */
  sceneNumbers?: Record<string, number>;
  durations?: Record<string, number>;
  onReorder: (orderedIds: string[]) => void;
  onDelete: (item: MediaItem) => void;
  onReplace: (item: MediaItem) => void;
  onCrop: (item: MediaItem) => void;
  onSelect?: (item: MediaItem) => void;
  selectedId?: string | null;
  disabled?: boolean;
  className?: string;
}

/**
 * The uploaded-image tray: thumbnail, scene number, duration and per-card actions,
 * reorderable by drag or by keyboard (grab with space, move with the arrow keys).
 */
export function MediaGrid({
  items,
  sceneNumbers,
  durations,
  onReorder,
  onDelete,
  onReplace,
  onCrop,
  onSelect,
  selectedId,
  disabled,
  className,
}: MediaGridProps) {
  // `order` is a local, optimistic ordering so a drag lands instantly instead of
  // waiting for the server round trip. It is re-derived during render whenever the
  // server's list changes — the documented way to reset state from props, and
  // cheaper than the effect-plus-setState version it replaces.
  const serverOrder = items.map((item) => item.id).join(",");
  const [order, setOrder] = useState<string[]>(() => items.map((item) => item.id));
  const [syncedWith, setSyncedWith] = useState(serverOrder);

  if (syncedWith !== serverOrder) {
    setSyncedWith(serverOrder);
    setOrder(items.map((item) => item.id));
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const byId = new Map(items.map((item) => [item.id, item]));
  const ordered = order.map((id) => byId.get(id)).filter(Boolean) as MediaItem[];

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = order.indexOf(String(active.id));
    const to = order.indexOf(String(over.id));
    const next = arrayMove(order, from, to);
    setOrder(next);
    onReorder(next);
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[restrictToParentElement]}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={order} strategy={rectSortingStrategy}>
        <ul
          className={cn(
            "grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6",
            className,
          )}
        >
          {ordered.map((item, index) => (
            <SortableMediaCard
              key={item.id}
              item={item}
              index={index}
              sceneNumber={sceneNumbers?.[item.id]}
              duration={durations?.[item.id]}
              onDelete={onDelete}
              onReplace={onReplace}
              onCrop={onCrop}
              onSelect={onSelect}
              selected={selectedId === item.id}
              disabled={disabled}
            />
          ))}
        </ul>
      </SortableContext>
    </DndContext>
  );
}

function SortableMediaCard({
  item,
  index,
  sceneNumber,
  duration,
  onDelete,
  onReplace,
  onCrop,
  onSelect,
  selected,
  disabled,
}: {
  item: MediaItem;
  index: number;
  sceneNumber?: number;
  duration?: number;
  onDelete: (item: MediaItem) => void;
  onReplace: (item: MediaItem) => void;
  onCrop: (item: MediaItem) => void;
  onSelect?: (item: MediaItem) => void;
  selected?: boolean;
  disabled?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    disabled,
  });

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "group relative overflow-hidden rounded-card border bg-elevated",
        selected ? "border-accent ring-2 ring-accent/25" : "border-line",
        isDragging && "z-10 opacity-80 shadow-lifted",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect?.(item)}
        className="block aspect-[9/16] w-full"
        aria-label={`Image ${index + 1}${sceneNumber ? `, scene ${sceneNumber}` : ""}`}
      >
                <img
          src={item.thumbnail_url ?? item.url}
          alt=""
          className="h-full w-full object-cover"
          loading="lazy"
          draggable={false}
        />
      </button>

      <span className="absolute left-1.5 top-1.5 rounded-md bg-black/70 px-1.5 py-0.5 text-2xs font-medium text-white backdrop-blur">
        {sceneNumber ? `Scene ${sceneNumber}` : `#${index + 1}`}
      </span>

      <button
        type="button"
        {...attributes}
        {...listeners}
        className={cn(
          "absolute right-1.5 top-1.5 cursor-grab rounded-md bg-black/70 p-1 text-white/80 backdrop-blur transition-opacity active:cursor-grabbing",
          disabled ? "hidden" : "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
        )}
        aria-label={`Reorder image ${index + 1}`}
      >
        <GripVertical className="h-3.5 w-3.5" aria-hidden />
      </button>

      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-gradient-to-t from-black/85 to-transparent px-1.5 pb-1.5 pt-5">
        <span className="truncate text-2xs text-white/80">
          {duration ? `${duration.toFixed(1)}s` : formatBytes(item.size_bytes)}
        </span>
        <span className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <IconAction label="Crop" onClick={() => onCrop(item)} disabled={disabled}>
            <Crop className="h-3.5 w-3.5" />
          </IconAction>
          <IconAction label="Replace" onClick={() => onReplace(item)} disabled={disabled}>
            <RefreshCw className="h-3.5 w-3.5" />
          </IconAction>
          <IconAction label="Delete" destructive onClick={() => onDelete(item)} disabled={disabled}>
            <Trash2 className="h-3.5 w-3.5" />
          </IconAction>
        </span>
      </div>
    </li>
  );
}

function IconAction({
  children,
  label,
  onClick,
  destructive,
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={cn(
        "rounded-md p-1 text-white/85 backdrop-blur transition-colors",
        destructive ? "bg-danger/70 hover:bg-danger" : "bg-black/60 hover:bg-black/80",
        disabled && "pointer-events-none opacity-40",
      )}
    >
      {children}
    </button>
  );
}
