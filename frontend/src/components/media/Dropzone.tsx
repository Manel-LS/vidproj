"use client";

import { useCallback, useRef, useState, type DragEvent } from "react";
import { ImagePlus, Loader2, UploadCloud } from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";

const DEFAULT_ACCEPT = ["image/jpeg", "image/png", "image/webp"];

export interface DropzoneProps {
  onFiles: (files: File[]) => void;
  accept?: string[];
  maxBytes?: number;
  maxFiles?: number;
  uploading?: boolean;
  progress?: number;
  disabled?: boolean;
  compact?: boolean;
  label?: string;
  hint?: string;
  className?: string;
}

/**
 * Drag-and-drop uploader.
 *
 * Client-side checks here are a courtesy — they give instant feedback and save a
 * round trip. The server re-validates everything by decoding the file, because a
 * MIME type and an extension are only claims.
 */
export function Dropzone({
  onFiles,
  accept = DEFAULT_ACCEPT,
  maxBytes = 15 * 1024 * 1024,
  maxFiles = 20,
  uploading = false,
  progress = 0,
  disabled = false,
  compact = false,
  label = "Drop your images here",
  hint,
  className,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);

  const handle = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return;
      const files = Array.from(fileList);
      const problems: string[] = [];
      const accepted: File[] = [];

      for (const file of files.slice(0, maxFiles)) {
        const typeOk =
          accept.includes(file.type) ||
          (file.type === "" && /\.(jpe?g|png|webp|mp3|wav)$/i.test(file.name));
        if (!typeOk) {
          problems.push(`${file.name} — unsupported file type`);
          continue;
        }
        if (file.size > maxBytes) {
          problems.push(`${file.name} — larger than ${formatBytes(maxBytes)}`);
          continue;
        }
        accepted.push(file);
      }

      if (files.length > maxFiles) {
        problems.push(`Only the first ${maxFiles} files were taken.`);
      }

      setRejected(problems);
      if (accepted.length) onFiles(accepted);
    },
    [accept, maxBytes, maxFiles, onFiles],
  );

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled || uploading) return;
    handle(event.dataTransfer.files);
  };

  return (
    <div className={className}>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled && !uploading) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !disabled && !uploading && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label={label}
        aria-disabled={disabled}
        className={cn(
          "relative flex w-full cursor-pointer flex-col items-center justify-center rounded-panel border-2 border-dashed text-center transition-colors",
          compact ? "gap-2 px-4 py-6" : "gap-3 px-6 py-12",
          dragging
            ? "border-accent bg-accent/8"
            : "border-line bg-surface/50 hover:border-accent/50 hover:bg-elevated/40",
          (disabled || uploading) && "cursor-not-allowed opacity-60",
        )}
      >
        <span
          className={cn(
            "flex items-center justify-center rounded-2xl bg-elevated text-accent",
            compact ? "h-9 w-9" : "h-12 w-12",
          )}
        >
          {uploading ? (
            <Loader2 className={cn("animate-spin", compact ? "h-4 w-4" : "h-5 w-5")} aria-hidden />
          ) : dragging ? (
            <UploadCloud className={compact ? "h-4 w-4" : "h-5 w-5"} aria-hidden />
          ) : (
            <ImagePlus className={compact ? "h-4 w-4" : "h-5 w-5"} aria-hidden />
          )}
        </span>

        <div>
          <p className={cn("font-medium text-ink", compact ? "text-sm" : "text-[15px]")}>
            {uploading ? `Uploading… ${progress}%` : dragging ? "Drop to upload" : label}
          </p>
          <p className="mt-1 text-xs text-muted">
            {hint ?? `JPG, PNG or WEBP · up to ${formatBytes(maxBytes)} each`}
          </p>
        </div>

        {uploading ? (
          <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden rounded-b-panel bg-line">
            <div
              className="h-full bg-accent transition-[width] duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        ) : null}

        <input
          ref={inputRef}
          type="file"
          multiple={maxFiles > 1}
          accept={accept.join(",")}
          className="sr-only"
          onChange={(event) => {
            handle(event.target.files);
            event.target.value = "";
          }}
          disabled={disabled || uploading}
        />
      </div>

      {rejected.length ? (
        <ul className="mt-2 space-y-1 text-xs text-danger" role="alert">
          {rejected.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
