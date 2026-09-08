/** The unified activity strip (requirement 17). */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { GenerationJob, ProjectJobs } from "@/lib/api/types";
import { GenerationActivity } from "./GenerationActivity";

const projectJobs = vi.fn();
vi.mock("@/lib/api/client", () => ({ api: { projectJobs: (...args: unknown[]) => projectJobs(...args) } }));

function job(overrides: Partial<GenerationJob> & Pick<GenerationJob, "type">): GenerationJob {
  return {
    id: Math.random().toString(36).slice(2),
    project_id: "p1",
    scene_id: null,
    provider: "",
    status: "completed",
    progress: 100,
    stage: "Done",
    error: "",
    external_job_id: "",
    result_media_id: null,
    result_url: null,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

function payload(items: GenerationJob[], extra: Partial<ProjectJobs> = {}): ProjectJobs {
  return {
    items,
    total: items.length,
    active: items.filter((j) => j.status === "queued" || j.status === "processing").length,
    progress: 0,
    current_stage: "",
    last_error: "",
    by_status: {},
    ...extra,
  };
}

function renderStrip() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GenerationActivity projectId="p1" />
    </QueryClientProvider>,
  );
}

describe("GenerationActivity", () => {
  beforeEach(() => projectJobs.mockReset());

  it("stays out of the way when the project has generated nothing", async () => {
    projectJobs.mockResolvedValue(payload([]));
    const { container } = renderStrip();
    // Nothing to report is not an empty box: the strip renders no markup at all.
    await vi.waitFor(() => expect(projectJobs).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the live stage and progress of the work in flight", async () => {
    projectJobs.mockResolvedValue(
      payload([job({ type: "render", status: "processing", stage: "Animating scene 2 of 6" })], {
        progress: 34,
      }),
    );
    renderStrip();

    expect(await screen.findByText("Animating scene 2 of 6")).toBeInTheDocument();
    expect(screen.getByText("34%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "34");
  });

  it("only lists steps that really ran, never an invented pipeline", async () => {
    projectJobs.mockResolvedValue(payload([job({ type: "voice" }), job({ type: "render" })]));
    renderStrip();

    expect(await screen.findByText("Voice-over")).toBeInTheDocument();
    expect(screen.getByText("Video")).toBeInTheDocument();
    // No image provider is configured in this deployment, so no "Images" step.
    expect(screen.queryByText("Images")).not.toBeInTheDocument();
    expect(screen.queryByText("Lip sync")).not.toBeInTheDocument();
  });

  it("reports a failure with the backend's own wording", async () => {
    projectJobs.mockResolvedValue(
      payload([job({ type: "voice", status: "failed", error: "No TTS provider is configured." })]),
    );
    renderStrip();

    expect(await screen.findByRole("alert")).toHaveTextContent("No TTS provider is configured.");
    expect(screen.getByText(/needs attention/i)).toBeInTheDocument();
  });

  it("counts repeated work of one kind instead of repeating the step", async () => {
    projectJobs.mockResolvedValue(
      payload([job({ type: "image" }), job({ type: "image" }), job({ type: "image" })]),
    );
    renderStrip();

    expect(await screen.findByText("Images")).toBeInTheDocument();
    expect(screen.getByText("×3")).toBeInTheDocument();
  });

  it("lets one failure surface even when other jobs of that kind succeeded", async () => {
    projectJobs.mockResolvedValue(
      payload([job({ type: "image" }), job({ type: "image", status: "failed", error: "Rate limited." })]),
    );
    renderStrip();

    expect(await screen.findByRole("alert")).toHaveTextContent("Rate limited.");
  });
});
