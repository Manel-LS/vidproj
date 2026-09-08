"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api/client";

type ToastTone = "info" | "success" | "warning" | "error";

interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastContextValue {
  push: (toast: Omit<Toast, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
  /** Surface a thrown error using the backend's own message. */
  fromError: (error: unknown, fallback?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const ICONS: Record<ToastTone, ReactNode> = {
  info: <Info className="h-4 w-4 text-accent" aria-hidden />,
  success: <CheckCircle2 className="h-4 w-4 text-positive" aria-hidden />,
  warning: <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />,
  error: <XCircle className="h-4 w-4 text-danger" aria-hidden />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (toast: Omit<Toast, "id">) => {
      counter.current += 1;
      const id = counter.current;
      setToasts((current) => [...current.slice(-3), { ...toast, id }]);
      const lifetime = toast.tone === "error" ? 8000 : 4500;
      window.setTimeout(() => dismiss(id), lifetime);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, description) => push({ tone: "success", title, description }),
      error: (title, description) => push({ tone: "error", title, description }),
      info: (title, description) => push({ tone: "info", title, description }),
      fromError: (error, fallback = "Something went wrong. Please try again.") => {
        if (error instanceof ApiError) {
          const details = Array.isArray(error.details)
            ? (error.details as Array<{ field?: string; problem?: string }>)
                .map((detail) => [detail.field, detail.problem].filter(Boolean).join(": "))
                .filter(Boolean)
                .slice(0, 3)
                .join(" · ")
            : undefined;
          push({ tone: "error", title: error.message, description: details });
          return;
        }
        push({
          tone: "error",
          title: fallback,
          description: error instanceof Error ? error.message : undefined,
        });
      },
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto flex animate-slide-up items-start gap-2.5 rounded-xl border bg-elevated px-3.5 py-3 shadow-lifted",
              toast.tone === "error" ? "border-danger/40" : "border-line",
            )}
          >
            <span className="mt-0.5">{ICONS[toast.tone]}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">{toast.title}</p>
              {toast.description ? (
                <p className="mt-0.5 break-words text-xs text-muted">{toast.description}</p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              className="rounded p-0.5 text-faint transition-colors hover:text-ink"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>.");
  return context;
}
