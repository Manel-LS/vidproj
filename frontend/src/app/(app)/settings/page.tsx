"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle, ExternalLink, Server } from "lucide-react";
import { Badge, Notice, Spinner } from "@/components/ui/Feedback";
import { Button } from "@/components/ui/Button";
import { API_BASE, api } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { cn, formatBytes } from "@/lib/utils";

/**
 * Settings is mostly a status page.
 *
 * Provider credentials live in the backend environment and are never exposed to the
 * browser — so this shows *whether* each capability is configured, and names the
 * environment variable to set, but never a key.
 */
export default function SettingsPage() {
  const { user, signOut } = useAuth();
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities });

  const data = capabilities.data;

  const providers = data
    ? [
        {
          name: "Video rendering",
          available: data.render.available,
          detail: data.render.available
            ? `${data.render.engine} · ${data.render.version.replace("ffmpeg version ", "").split(" ")[0]}`
            : data.render.message,
          env: "FFMPEG_BINARY",
          required: true,
        },
        {
          name: "AI video planner",
          available: data.ai_planner.available,
          detail: data.ai_planner.available
            ? data.ai_planner.display_name
            : data.ai_planner.message,
          env: "ANTHROPIC_API_KEY / OPENAI_API_KEY",
          required: false,
        },
        {
          name: "AI voice-over",
          available: data.voiceover.available,
          detail: data.voiceover.available ? data.voiceover.display_name : data.voiceover.message,
          env: "TTS_PROVIDER + ELEVENLABS_API_KEY / OPENAI_API_KEY",
          required: false,
        },
        {
          name: "AI Motion (image → video)",
          available: data.ai_motion.available,
          detail: data.ai_motion.available ? data.ai_motion.display_name : data.ai_motion.message,
          env: "I2V_PROVIDER + the provider's key",
          required: false,
        },
      ]
    : [];

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 lg:px-8">
      <header className="mb-7">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">Your account and what this deployment can do.</p>
      </header>

      <section className="card mb-6 p-5">
        <h2 className="text-sm font-semibold">Account</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted">Name</dt>
            <dd className="text-ink">{user?.full_name || "—"}</dd>
          </div>
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted">Email</dt>
            <dd className="truncate text-ink">{user?.email}</dd>
          </div>
        </dl>
        <Button variant="secondary" size="sm" className="mt-5" onClick={signOut}>
          Sign out
        </Button>
      </section>

      <section className="card mb-6 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Capabilities</h2>
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
          >
            API docs
            <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        </div>

        {capabilities.isLoading ? (
          <Spinner label="Checking the server…" />
        ) : capabilities.isError ? (
          <Notice tone="danger" title="Could not reach the backend">
            Check that the API is running at <code className="font-mono">{API_BASE}</code>.
          </Notice>
        ) : (
          <ul className="divide-y divide-line">
            {providers.map((provider) => (
              <li key={provider.name} className="flex items-start gap-3 py-3">
                {provider.available ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-positive" aria-hidden />
                ) : (
                  <Circle
                    className={cn(
                      "mt-0.5 h-4 w-4 shrink-0",
                      provider.required ? "text-danger" : "text-faint",
                    )}
                    aria-hidden
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-sm text-ink">
                    {provider.name}
                    {provider.available ? (
                      <Badge tone="success">Configured</Badge>
                    ) : provider.required ? (
                      <Badge tone="danger">Missing</Badge>
                    ) : (
                      <Badge>Optional</Badge>
                    )}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">{provider.detail}</p>
                  {!provider.available ? (
                    <p className="mt-1 font-mono text-2xs text-faint">
                      Set {provider.env} in the backend environment.
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {data ? (
        <section className="card p-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Server className="h-4 w-4 text-muted" aria-hidden />
            Deployment
          </h2>
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <Row label="Storage" value={data.storage.provider} />
            <Row label="Job queue" value={`${data.queue.provider} (set: ${data.queue.configured})`} />
            <Row label="Frame rate" value={`${data.render.fps} fps`} />
            <Row label="Transitions" value={`${data.render.transitions.length} available`} />
            <Row label="Max image size" value={formatBytes(data.limits.max_image_bytes)} />
            <Row label="Max audio size" value={formatBytes(data.limits.max_audio_bytes)} />
            <Row label="Images per project" value={String(data.limits.max_images_per_project)} />
            <Row label="API" value={API_BASE} />
          </dl>

          <details className="mt-5">
            <summary className="cursor-pointer text-xs text-muted hover:text-ink">
              Fonts resolved for rendering
            </summary>
            <ul className="mt-2 space-y-1 font-mono text-2xs text-faint">
              {Object.entries(data.fonts).map(([key, value]) => (
                <li key={key} className="truncate">
                  {key}: {value}
                </li>
              ))}
            </ul>
          </details>
        </section>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-2xs uppercase tracking-wider text-faint">{label}</dt>
      <dd className="truncate text-sm text-ink">{value}</dd>
    </div>
  );
}
