/**
 * The per-scene AI controls: generated image and lip sync.
 *
 * Both endpoints existed and were tested server-side; nothing in the editor called
 * them. These tests cover the part that is genuinely the UI's job — refusing to
 * offer an action the deployment or the project cannot honour, and saying why.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SceneProperties } from "./SceneProperties";
import type { Capabilities, EditorOptions, MediaItem, Scene } from "@/lib/api/types";

const OPTIONS: EditorOptions = {
  animations: ["none", "ken_burns"],
  transitions: ["none", "fade"],
  text_positions: ["lower_third"],
  text_animations: ["fade"],
  text_roles: ["title", "subtitle", "cta", "caption"],
  text_backgrounds: ["none"],
  font_families: ["sans_bold"],
  styles: ["product_showcase"],
  subtitle_styles: [],
};

const IMAGE: MediaItem = {
  id: "media-1",
  kind: "image",
  source: "upload",
  url: "http://localhost:8000/api/v1/files/a.jpg",
  thumbnail_url: null,
  original_filename: "a.jpg",
  content_type: "image/jpeg",
  size_bytes: 10,
  width: 1080,
  height: 1920,
  duration_seconds: null,
  position: 0,
  created_at: new Date().toISOString(),
  analysis: {},
};

function scene(overrides: Partial<Scene> = {}): Scene {
  return {
    id: "scene-1",
    order: 0,
    media_id: "media-1",
    duration: 3,
    animation: "ken_burns",
    animation_intensity: 1,
    focus_x: 0.5,
    focus_y: 0.5,
    transition: "fade",
    transition_duration: 0.4,
    texts: [],
    background_color: "#000000",
    note: "",
    image_prompt: "",
    ai_motion: null,
    start_time: 0,
    media: IMAGE,
    ...overrides,
  };
}

function capabilities(overrides: Record<string, unknown> = {}) {
  return {
    image: {
      available: true,
      provider: "openai",
      display_name: "OpenAI",
      message: "",
      supported_aspect_ratios: ["9:16"],
      supports_reference_image: true,
    },
    lipsync: {
      available: true,
      provider: "replicate",
      display_name: "Replicate",
      message: "",
      max_clip_seconds: 30,
      needs_public_urls: false,
    },
    ai_motion: {
      available: false,
      provider: "none",
      display_name: "Not configured",
      message: "AI Motion is unavailable because no video generation provider is configured.",
      supported_durations: [5],
      supported_aspect_ratios: ["9:16"],
    },
    ...overrides,
  } as unknown as Capabilities;
}

function renderPanel(props: Partial<Parameters<typeof SceneProperties>[0]> = {}) {
  const onGenerateImage = vi.fn();
  const onGenerateLipsync = vi.fn();
  const onChange = vi.fn();
  render(
    <SceneProperties
      scene={scene()}
      sceneIndex={0}
      isFirst
      images={[IMAGE]}
      options={OPTIONS}
      capabilities={capabilities()}
      onChange={onChange}
      onGenerateAiMotion={vi.fn()}
      onGenerateImage={onGenerateImage}
      onGenerateLipsync={onGenerateLipsync}
      {...props}
    />,
  );
  return { onGenerateImage, onGenerateLipsync, onChange };
}

describe("AI image", () => {
  it("explains why the control is off instead of hiding it", () => {
    renderPanel({
      capabilities: capabilities({
        image: {
          available: false,
          provider: "none",
          display_name: "Not configured",
          message: "Image generation is unavailable because no provider is configured.",
          supported_aspect_ratios: [],
          supports_reference_image: false,
        },
      }),
    });
    expect(screen.getByText(/no provider is configured/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate with/i })).not.toBeInTheDocument();
  });

  it("will not queue an empty prompt", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /generate with openai/i })).toBeDisabled();
  });

  it("seeds the field from the scene and offers a regeneration", () => {
    renderPanel({ scene: scene({ image_prompt: "A red chechia, warm light" }) });
    expect(screen.getByLabelText(/image prompt/i)).toHaveValue("A red chechia, warm light");
    // The scene already has an image, so the wording is not "Generate".
    expect(screen.getByRole("button", { name: /regenerate with openai/i })).toBeEnabled();
  });

  it("saves the prompt on blur so it survives without generating", async () => {
    const { onChange } = renderPanel();
    const field = screen.getByLabelText(/image prompt/i);
    await userEvent.type(field, "A quiet street at dusk");
    await userEvent.tab();
    expect(onChange).toHaveBeenCalledWith({ image_prompt: "A quiet street at dusk" });
  });

  it("queues the prompt shown in the field", async () => {
    const { onGenerateImage } = renderPanel({ scene: scene({ image_prompt: "Golden hour" }) });
    await userEvent.click(screen.getByRole("button", { name: /regenerate with openai/i }));
    expect(onGenerateImage).toHaveBeenCalledWith("Golden hour");
  });
});

describe("Lip sync", () => {
  it("refuses without a clip and says which step is missing", () => {
    renderPanel({ voiceReady: true });
    expect(screen.getByRole("button", { name: /sync with replicate/i })).toBeDisabled();
    expect(screen.getByText(/generate this scene's motion clip first/i)).toBeInTheDocument();
  });

  it("refuses without a narration and says which step is missing", () => {
    renderPanel({
      scene: scene({
        ai_motion: {
          enabled: true,
          prompt: "",
          generated_media_id: "clip-1",
          provider: "runway",
          job_reference: null,
        },
      }),
      voiceReady: false,
    });
    expect(screen.getByRole("button", { name: /sync with replicate/i })).toBeDisabled();
    expect(screen.getByText(/generate the voice-over first/i)).toBeInTheDocument();
  });

  it("runs once a clip and a narration both exist", async () => {
    const { onGenerateLipsync } = renderPanel({
      scene: scene({
        ai_motion: {
          enabled: true,
          prompt: "",
          generated_media_id: "clip-1",
          provider: "runway",
          job_reference: null,
        },
      }),
      voiceReady: true,
    });
    const button = screen.getByRole("button", { name: /sync with replicate/i });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onGenerateLipsync).toHaveBeenCalledTimes(1);
  });

  it("stays available from the silent original once a scene is already synced", () => {
    renderPanel({
      scene: scene({
        ai_motion: {
          enabled: true,
          prompt: "",
          generated_media_id: "speaking-1",
          silent_media_id: "silent-1",
          lipsync_provider: "replicate",
          provider: "runway",
          job_reference: null,
        },
      }),
      voiceReady: true,
    });
    expect(screen.getByRole("button", { name: /sync with replicate/i })).toBeEnabled();
    expect(screen.getByText(/silent original is kept/i)).toBeInTheDocument();
  });
});
