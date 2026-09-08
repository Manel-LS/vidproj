/** Scene editing and video configuration tests (requirement 29). */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SceneProperties } from "./SceneProperties";
import { StyleCard } from "@/components/styles/StyleCard";
import type { Capabilities, EditorOptions, MediaItem, Scene, StylePreset } from "@/lib/api/types";
import { useEditorStore } from "@/lib/store/editor";

const OPTIONS: EditorOptions = {
  animations: ["none", "zoom_in", "pan_right", "ken_burns"],
  transitions: ["none", "fade", "zoom", "wipe"],
  text_positions: ["top", "center", "lower_third", "bottom"],
  text_animations: ["none", "fade", "pop", "typewriter"],
  text_roles: ["title", "subtitle", "cta", "caption"],
  text_backgrounds: ["none", "box", "pill", "gradient"],
  font_families: ["sans_bold", "sans", "serif"],
  styles: ["product_showcase", "tiktok_trend"],
  subtitle_styles: [],
};

const IMAGE: MediaItem = {
  id: "media-1",
  kind: "image",
  source: "upload",
  url: "http://localhost:8000/api/v1/files/a.jpg",
  thumbnail_url: "http://localhost:8000/api/v1/files/a-thumb.jpg",
  original_filename: "product.jpg",
  content_type: "image/jpeg",
  size_bytes: 1000,
  width: 1200,
  height: 1600,
  duration_seconds: null,
  position: 1,
  created_at: new Date().toISOString(),
  analysis: {},
};

const SCENE: Scene = {
  id: "scene-1",
  order: 1,
  media_id: "media-1",
  duration: 3,
  animation: "ken_burns",
  animation_intensity: 1,
  focus_x: 0.5,
  focus_y: 0.45,
  transition: "fade",
  transition_duration: 0.4,
  texts: [
    {
      id: "text-1",
      role: "subtitle",
      content: "Everything you need",
      position: "lower_third",
      align: "center",
      animation: "fade",
      font_family: "sans_bold",
      font_size: 64,
      font_weight: 700,
      color: "#FFFFFF",
      letter_spacing: 0,
      line_height: 1.16,
      uppercase: false,
      opacity: 1,
      background: "none",
      background_color: "#000000",
      background_opacity: 0.45,
      shadow: true,
      max_width_pct: 0.84,
      offset_y_pct: 0,
      offset_x_pct: 0,
      start: 0.15,
      duration: null,
      animation_duration: 0.45,
    },
  ],
  background_color: "#000000",
  note: "content scene · ken burns",
  image_prompt: "",
  ai_motion: null,
  start_time: 2.6,
  media: IMAGE,
};

const CAPABILITIES = {
  ai_motion: {
    available: false,
    provider: "none",
    display_name: "Not configured",
    message: "AI Motion is unavailable because no video generation provider is configured.",
    supported_durations: [5],
    supported_aspect_ratios: ["9:16"],
  },
} as unknown as Capabilities;

function renderPanel(overrides: Partial<Parameters<typeof SceneProperties>[0]> = {}) {
  const onChange = vi.fn();
  useEditorStore.getState().selectText("text-1");
  render(
    <SceneProperties
      scene={SCENE}
      sceneIndex={1}
      isFirst={false}
      images={[IMAGE]}
      options={OPTIONS}
      capabilities={CAPABILITIES}
      onChange={onChange}
      onGenerateAiMotion={vi.fn()}
      {...overrides}
    />,
  );
  return { onChange };
}

describe("SceneProperties", () => {
  it("prompts to pick a scene when none is selected", () => {
    render(
      <SceneProperties
        scene={null}
        sceneIndex={0}
        isFirst
        images={[]}
        options={OPTIONS}
        capabilities={CAPABILITIES}
        onChange={vi.fn()}
        onGenerateAiMotion={vi.fn()}
      />,
    );
    expect(screen.getByText(/select a scene/i)).toBeInTheDocument();
  });

  it("changes the camera move", async () => {
    const { onChange } = renderPanel();
    await userEvent.selectOptions(screen.getByLabelText(/camera move/i), "pan_right");
    expect(onChange).toHaveBeenCalledWith({ animation: "pan_right" });
  });

  it("changes the transition and its length", async () => {
    const { onChange } = renderPanel();
    await userEvent.selectOptions(screen.getByLabelText(/^type$/i), "wipe");
    expect(onChange).toHaveBeenCalledWith({ transition: "wipe" });

    const slider = screen.getByLabelText(/^length$/i);
    fireChange(slider, "0.8");
    expect(onChange).toHaveBeenCalledWith({ transition_duration: 0.8 });
  });

  it("hides the transition controls on the first scene and explains why", () => {
    renderPanel({ isFirst: true });
    expect(screen.getByText(/opens on a cut/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^type$/i)).not.toBeInTheDocument();
  });

  it("changes the scene duration", () => {
    const { onChange } = renderPanel();
    fireChange(screen.getByLabelText(/^duration$/i), "5.5");
    expect(onChange).toHaveBeenCalledWith({ duration: 5.5 });
  });

  it("edits the on-screen text", async () => {
    const { onChange } = renderPanel();
    const textarea = screen.getByLabelText(/^content$/i);
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "New copy");

    const last = onChange.mock.calls.at(-1)![0] as { texts: Array<{ content: string }> };
    expect(last.texts[0].content).toBeTruthy();
  });

  it("adds and removes a text layer", async () => {
    const { onChange } = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /^add$/i }));
    expect((onChange.mock.calls.at(-1)![0] as { texts: unknown[] }).texts).toHaveLength(2);

    onChange.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /remove this text/i }));
    expect((onChange.mock.calls.at(-1)![0] as { texts: unknown[] }).texts).toHaveLength(0);
  });

  it("moves the focal point when the thumbnail is clicked", async () => {
    const { onChange } = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: /set the focal point/i }));
    const call = onChange.mock.calls.find((entry) => "focus_x" in (entry[0] as object));
    expect(call).toBeTruthy();
  });

  it("swaps the scene's image", async () => {
    const { onChange } = renderPanel();
    await userEvent.selectOptions(screen.getByLabelText(/source image/i), "");
    expect(onChange).toHaveBeenCalledWith({ media_id: null });
  });

  it("reports AI Motion as unavailable rather than offering a broken button", () => {
    renderPanel();
    expect(
      screen.getByText(/no video generation provider is configured/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate with/i })).not.toBeInTheDocument();
  });
});

describe("StyleCard", () => {
  const PRESET: StylePreset = {
    key: "tiktok_trend",
    name: "TikTok Trend",
    description: "Fast cuts, punchy zooms and high-energy pacing.",
    tagline: "Stop the scroll",
    gradient: ["#F43F5E", "#8B5CF6"],
    scene_seconds: [1.2, 2],
    transition_seconds: 0.22,
    motion_intensity: 1.6,
    animations: ["dynamic_zoom"],
    transitions: ["zoom"],
    text_position: "center",
    text_animation: "pop",
    default_cta: "Get yours now",
    typography: {
      family: "sans_bold",
      title_size: 100,
      subtitle_size: 64,
      caption_size: 46,
      color: "#FFFFFF",
      accent_color: "#FDE047",
      background: "pill",
      background_color: "#111111",
      background_opacity: 0.55,
      letter_spacing: -1,
      uppercase: true,
      align: "center",
      shadow: true,
    },
  };

  it("shows the style and reports its selected state", async () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <StyleCard preset={PRESET} selected={false} onSelect={onSelect} />,
    );

    const card = screen.getByRole("button");
    expect(card).toHaveAttribute("aria-pressed", "false");
    expect(within(card).getByText("TikTok Trend")).toBeInTheDocument();
    expect(within(card).getByText(/1.2–2s scenes/)).toBeInTheDocument();

    await userEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith("tiktok_trend");

    rerender(<StyleCard preset={PRESET} selected onSelect={onSelect} />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });
});

/** Range inputs need a native change event to update React state. */
function fireChange(element: HTMLElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("change", { bubbles: true }));
}
