/** Project language, and honesty about which voices really exist. */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Capabilities, LanguageSupport } from "@/lib/api/types";
import { LanguageSelect } from "./LanguageSelect";

const DERJA: LanguageSupport = {
  code: "tn",
  label: "Tunisian Arabic (derja)",
  rtl: true,
  supported: true,
  exact: true,
  voice_id: "ar-TN-HediNeural",
  note: "",
};

const ENGLISH: LanguageSupport = {
  code: "en",
  label: "English",
  rtl: false,
  supported: true,
  exact: true,
  voice_id: "en-US-AriaNeural",
  note: "",
};

function capabilities(languages: LanguageSupport[], available = true) {
  return {
    voiceover: {
      available,
      provider: available ? "edge" : "none",
      display_name: available ? "Edge" : "Not configured",
      message: "",
      voices: [],
      languages,
    },
  } as unknown as Capabilities;
}

describe("LanguageSelect", () => {
  it("offers the languages the server reports", () => {
    render(
      <LanguageSelect value="en" capabilities={capabilities([ENGLISH, DERJA])} onChange={vi.fn()} />,
    );
    const select = screen.getByLabelText(/language/i);
    expect(select).toHaveValue("en");
    expect(screen.getByRole("option", { name: "Tunisian Arabic (derja)" })).toBeInTheDocument();
  });

  it("still offers every language when capabilities have not loaded", () => {
    // The language drives the planner and the subtitle direction, so the control
    // must work in a deployment with no text-to-speech at all.
    render(<LanguageSelect value="en" onChange={vi.fn()} />);
    expect(screen.getByRole("option", { name: "Tunisian Arabic (derja)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "French" })).toBeInTheDocument();
  });

  it("reports the chosen language code", async () => {
    const onChange = vi.fn();
    render(
      <LanguageSelect value="en" capabilities={capabilities([ENGLISH, DERJA])} onChange={onChange} />,
    );
    await userEvent.selectOptions(screen.getByLabelText(/language/i), "tn");
    expect(onChange).toHaveBeenCalledWith("tn");
  });

  it("says so when the provider has no voice for the language", () => {
    render(
      <LanguageSelect
        value="tn"
        capabilities={capabilities([
          { ...DERJA, supported: false, exact: false, voice_id: null, note: "No Tunisian Arabic (derja) voice from this provider." },
        ])}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/no tunisian arabic \(derja\) voice/i);
  });

  it("admits a substituted accent instead of passing it off as a match", () => {
    render(
      <LanguageSelect
        value="tn"
        capabilities={capabilities([
          { ...DERJA, exact: false, voice_id: "ar-EG-SalmaNeural", note: "No Tunisian Arabic (derja) voice from this provider; the closest available accent is 'ar-EG-SalmaNeural'." },
        ])}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/closest available accent is 'ar-EG-SalmaNeural'/);
  });

  it("says nothing about voices when no provider is configured at all", () => {
    // Complaining per language about a provider that does not exist would send the
    // user looking for the wrong problem; the voice-over panel already explains it.
    render(
      <LanguageSelect
        value="tn"
        capabilities={capabilities([{ ...DERJA, supported: false, exact: false, voice_id: null, note: "x" }], false)}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
