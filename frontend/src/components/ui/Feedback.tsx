"use client";

import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Requirement 27: never fail silently. Every one of these takes a message the user
 * can act on — components pass the backend's own wording straight through.
 */

type Tone = "info" | "success" | "warning" | "danger";

const TONES: Record<Tone, { wrap: string; icon: ReactNode }> = {
  info: {
    wrap: "border-accent/25 bg-accent/10 text-ink",
    icon: <Info className="h-4 w-4 shrink-0 text-accent" aria-hidden />,
  },
  success: {
    wrap: "border-positive/25 bg-positive/10 text-ink",
    icon: <CheckCircle2 className="h-4 w-4 shrink-0 text-positive" aria-hidden />,
  },
  warning: {
    wrap: "border-warning/25 bg-warning/10 text-ink",
    icon: <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-hidden />,
  },
  danger: {
    wrap: "border-danger/30 bg-danger/10 text-ink",
    icon: <XCircle className="h-4 w-4 shrink-0 text-danger" aria-hidden />,
  },
};

export function Notice({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const style = TONES[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-sm", style.wrap, className)}
    >
      <span className="mt-0.5">{style.icon}</span>
      <div className="min-w-0 flex-1">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className={cn("text-muted", title && "mt-0.5")}>{children}</div> : null}
      </div>
      {action}
    </div>
  );
}

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-muted" role="status">
      <Loader2 className={cn("h-4 w-4 animate-spin", className)} aria-hidden />
      {label ? <span className="text-sm">{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-panel border border-dashed border-line px-6 py-14 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-elevated text-muted">
          {icon}
        </div>
      ) : null}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {description ? <p className="mt-1.5 max-w-sm text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  className?: string;
}) {
  const tones = {
    neutral: "bg-elevated text-muted border-line",
    accent: "bg-accent/12 text-accent border-accent/25",
    success: "bg-positive/12 text-positive border-positive/25",
    warning: "bg-warning/12 text-warning border-warning/25",
    danger: "bg-danger/12 text-danger border-danger/25",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 text-2xs font-medium",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ProgressBar({
  value,
  className,
  tone = "accent",
}: {
  value: number;
  className?: string;
  tone?: "accent" | "success";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-line", className)}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500 ease-out",
          tone === "accent" ? "bg-accent" : "bg-positive",
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
