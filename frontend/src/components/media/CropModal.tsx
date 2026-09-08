"use client";

import { useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type { MediaItem, VideoFormat } from "@/lib/api/types";
import { FORMAT_DIMENSIONS } from "@/lib/video/timeline";
import { clamp, cn } from "@/lib/utils";

type Rect = { x: number; y: number; width: number; height: number };

const RATIOS: Array<{ key: string; label: string; value: number | null }> = [
  { key: "free", label: "Free", value: null },
  { key: "9:16", label: "9:16", value: 9 / 16 },
  { key: "4:5", label: "4:5", value: 4 / 5 },
  { key: "1:1", label: "1:1", value: 1 },
  { key: "16:9", label: "16:9", value: 16 / 9 },
];

function aspectFor(value: VideoFormat): number {
  const [w, h] = FORMAT_DIMENSIONS[value] ?? [9, 16];
  return w / h;
}

/** The largest centred rectangle of `ratio` that fits inside the image. */
function fitRect(scale: number, ratio: number | null, item: MediaItem): Rect {
  const imageRatio = (item.width ?? 1) / (item.height ?? 1);
  if (ratio === null) {
    return { x: (1 - scale) / 2, y: (1 - scale) / 2, width: scale, height: scale };
  }
  let width = scale;
  let height = (width * imageRatio) / ratio;
  if (height > scale) {
    height = scale;
    width = (height * ratio) / imageRatio;
  }
  return { x: (1 - width) / 2, y: (1 - height) / 2, width, height };
}

/**
 * Crop tool.
 *
 * Coordinates are normalised [0, 1] so the backend can apply the same rectangle to
 * the original file regardless of the size shown here.
 *
 * The caller keys this component by media id, so opening a different image mounts a
 * fresh instance with its own initial rectangle — no effect syncing state to props.
 */
export function CropModal({
  open,
  media,
  format,
  onClose,
  onApply,
  saving,
}: {
  open: boolean;
  media: MediaItem | null;
  format: VideoFormat;
  onClose: () => void;
  onApply: (rect: Rect) => void;
  saving?: boolean;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [ratioKey, setRatioKey] = useState<string>(format);
  const [rect, setRect] = useState<Rect>(() =>
    media ? fitRect(0.86, aspectFor(format), media) : { x: 0.1, y: 0.1, width: 0.8, height: 0.8 },
  );
  const drag = useRef<{ mode: "move" | "resize"; startX: number; startY: number; origin: Rect } | null>(null);

  const targetRatio = useMemo(() => {
    const found = RATIOS.find((entry) => entry.key === ratioKey);
    if (found) return found.value;
    const [w, h] = FORMAT_DIMENSIONS[format] ?? [9, 16];
    return w / h;
  }, [ratioKey, format]);

  function applyRatio(key: string) {
    setRatioKey(key);
    if (!media) return;
    const entry = RATIOS.find((item) => item.key === key);
    setRect(fitRect(0.86, entry ? entry.value : targetRatio, media));
  }

  function onPointerDown(event: React.PointerEvent, mode: "move" | "resize") {
    event.preventDefault();
    event.stopPropagation();
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
    drag.current = { mode, startX: event.clientX, startY: event.clientY, origin: rect };
  }

  function onPointerMove(event: React.PointerEvent) {
    const state = drag.current;
    const frame = frameRef.current;
    if (!state || !frame) return;
    const bounds = frame.getBoundingClientRect();
    const dx = (event.clientX - state.startX) / bounds.width;
    const dy = (event.clientY - state.startY) / bounds.height;

    if (state.mode === "move") {
      setRect({
        ...state.origin,
        x: clamp(state.origin.x + dx, 0, 1 - state.origin.width),
        y: clamp(state.origin.y + dy, 0, 1 - state.origin.height),
      });
      return;
    }

    let width = clamp(state.origin.width + dx, 0.1, 1 - state.origin.x);
    let height = clamp(state.origin.height + dy, 0.1, 1 - state.origin.y);

    if (targetRatio !== null && ratioKey !== "free" && media) {
      const imageRatio = (media.width ?? 1) / (media.height ?? 1);
      height = clamp((width * imageRatio) / targetRatio, 0.1, 1 - state.origin.y);
      width = clamp((height * targetRatio) / imageRatio, 0.1, 1 - state.origin.x);
    }
    setRect({ ...state.origin, width, height });
  }

  function endDrag() {
    drag.current = null;
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Crop image"
      description="Drag to reposition, or pull the corner to resize. The crop is applied to the original file."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={() => onApply(rect)} loading={saving}>
            Apply crop
          </Button>
        </>
      }
    >
      {media ? (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {RATIOS.map((entry) => (
              <button
                key={entry.key}
                type="button"
                onClick={() => applyRatio(entry.key)}
                className={cn(
                  "rounded-lg border px-2.5 py-1 text-xs transition-colors",
                  ratioKey === entry.key
                    ? "border-accent bg-accent/12 text-accent"
                    : "border-line text-muted hover:text-ink",
                )}
              >
                {entry.label}
              </button>
            ))}
          </div>

          <div
            ref={frameRef}
            className="checkerboard relative mx-auto max-h-[52vh] w-fit select-none overflow-hidden rounded-xl"
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerLeave={endDrag}
          >
                        <img
              src={media.url}
              alt=""
              className="max-h-[52vh] w-auto select-none"
              draggable={false}
            />

            <div className="pointer-events-none absolute inset-0 bg-black/55" />

            <div
              className="absolute cursor-move border-2 border-white/90 shadow-[0_0_0_9999px_rgba(0,0,0,0.0)]"
              style={{
                left: `${rect.x * 100}%`,
                top: `${rect.y * 100}%`,
                width: `${rect.width * 100}%`,
                height: `${rect.height * 100}%`,
                boxShadow: "0 0 0 9999px rgba(0,0,0,0.45)",
              }}
              onPointerDown={(event) => onPointerDown(event, "move")}
              role="application"
              aria-label="Crop area"
            >
              {/* Rule-of-thirds guides */}
              <span className="pointer-events-none absolute inset-y-0 left-1/3 w-px bg-white/25" />
              <span className="pointer-events-none absolute inset-y-0 left-2/3 w-px bg-white/25" />
              <span className="pointer-events-none absolute inset-x-0 top-1/3 h-px bg-white/25" />
              <span className="pointer-events-none absolute inset-x-0 top-2/3 h-px bg-white/25" />

              <span
                className="absolute -bottom-2 -right-2 h-5 w-5 cursor-nwse-resize rounded-full border-2 border-white bg-accent"
                onPointerDown={(event) => onPointerDown(event, "resize")}
                role="slider"
                aria-label="Resize crop"
                aria-valuenow={Math.round(rect.width * 100)}
                tabIndex={0}
              />
            </div>
          </div>

          <p className="mt-3 text-center text-xs text-faint">
            {Math.round(rect.width * (media.width ?? 0))} ×{" "}
            {Math.round(rect.height * (media.height ?? 0))} px
          </p>
        </>
      ) : null}
    </Modal>
  );
}
