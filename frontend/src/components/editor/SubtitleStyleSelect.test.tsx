/**
 * The subtitle style control.
 *
 * The behaviour that matters is the honesty about highlighting: word-by-word needs
 * per-word timings from the voice provider, and the two reasons they can be missing
 * — the provider cannot report them, or this narration predates them — call for
 * different advice. Collapsing them into one message would send the user to fix the
 * wrong thing.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Capabilities, ProjectDetail, SubtitleStyleKey, VoiceOver } from "@/lib/api/types";
import { SubtitleStyleSelect } from "./SubtitleStyleSelect";

function voiceOver(overrides: Partial<VoiceOver> = {}): VoiceOver {
  return {
    id: "vo-1",
    enabled: true,
    script: "Bonjour a tous.",
    status: "ready",
    provider: "edge",
    voice_id: "fr-FR-DeniseNeural",
    volume: 1,
    duck_music_to: 0.28,
    error: "",
    media: { id: "m", url: "http://x/a.mp3" } as VoiceOver["media"],
    word_timings: [],
    has_word_timings: false,
    ...overrides,
  };
}

function project(style: SubtitleStyleKey, voice: VoiceOver | null = null): ProjectDetail {
  return { subtitle_style: style, voice_over: voice } as unknown as ProjectDetail;
}

function capabilities(supportsWordTimings: boolean) {
  return {
    voiceover: { available: true, supports_word_timings: supportsWordTimings },
  } as unknown as Capabilities;
}

describe("SubtitleStyleSelect", () => {
  it("offers the styles the server published", () => {
    render(
      <SubtitleStyleSelect
        project={project("none")}
        options={[
          { key: "none", name: "No subtitles", description: "" },
          { key: "tiktok", name: "TikTok", description: "Big and uppercase." },
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("option", { name: "TikTok" })).toBeInTheDocument();
  });

  it("still works before the server has answered", () => {
    // The preview can draw a band without /options; the control must not be empty.
    render(<SubtitleStyleSelect project={project("none")} onChange={vi.fn()} />);
    expect(screen.getByRole("option", { name: "Cinematic" })).toBeInTheDocument();
  });

  it("reports the chosen style", async () => {
    const onChange = vi.fn();
    render(<SubtitleStyleSelect project={project("none")} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText(/subtitles/i), "bold");
    expect(onChange).toHaveBeenCalledWith("bold");
  });

  it("says nothing when subtitles are switched off", () => {
    render(
      <SubtitleStyleSelect
        project={project("none")}
        capabilities={capabilities(true)}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("points at the missing voice-over when there is none", () => {
    render(
      <SubtitleStyleSelect
        project={project("tiktok")}
        capabilities={capabilities(true)}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/generate one and they will appear/i);
  });

  it("offers a regeneration when the provider could have timed this narration", () => {
    render(
      <SubtitleStyleSelect
        project={project("tiktok", voiceOver({ has_word_timings: false }))}
        capabilities={capabilities(true)}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/regenerate the voice-over/i);
  });

  it("does not suggest regenerating when the provider cannot time words at all", () => {
    render(
      <SubtitleStyleSelect
        project={project("tiktok", voiceOver({ has_word_timings: false }))}
        capabilities={capabilities(false)}
        onChange={vi.fn()}
      />,
    );
    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent(/does not report word timings/i);
    expect(notice).not.toHaveTextContent(/regenerate/i);
  });

  it("stays quiet once the narration really carries timings", () => {
    render(
      <SubtitleStyleSelect
        project={project(
          "tiktok",
          voiceOver({ has_word_timings: true, word_timings: [{ text: "un", start: 0, duration: 0.2 }] }),
        )}
        capabilities={capabilities(true)}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
