/**
 * The brand kit form.
 *
 * What is worth testing here is not that inputs hold text. It is that the form
 * refuses to offer what the server cannot honour yet — the logo upload before the
 * kit exists — and that the preview reflects the colours being chosen, because a
 * hex code in a field is impossible to judge and the whole point of a kit is that
 * those three colours land on every video.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BrandKit } from "@/lib/api/types";
import { BrandKitCard, BrandKitForm } from "./BrandKitForm";

const KIT: BrandKit = {
  id: "kit-1",
  name: "Nova",
  brand_name: "Nova Stationery",
  slogan: "La rentrée, en mieux",
  primary_color: "#FFFFFF",
  accent_color: "#39E08B",
  background_color: "#101014",
  font_family: "sans_bold",
  logo_media_id: "m1",
  logo_url: "http://localhost:8000/api/v1/files/logo.png",
  logo_position: "bottom_right",
  logo_scale: 0.2,
  logo_opacity: 0.85,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("BrandKitForm", () => {
  it("will not save a kit with no name", () => {
    render(<BrandKitForm kit={null} onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: /create brand kit/i })).toBeDisabled();
  });

  it("sends what was typed", async () => {
    const onSave = vi.fn();
    render(<BrandKitForm kit={null} onSave={onSave} />);

    await userEvent.type(screen.getByLabelText(/kit name/i), "Nova");
    await userEvent.type(screen.getByLabelText(/brand name/i), "Nova Stationery");
    await userEvent.click(screen.getByRole("button", { name: /create brand kit/i }));

    expect(onSave.mock.calls[0][0]).toMatchObject({ name: "Nova", brand_name: "Nova Stationery" });
  });

  it("waits for a saved kit before offering a logo", () => {
    // The upload endpoint needs a kit id, so offering the button first would only
    // produce an error the user could not act on.
    render(<BrandKitForm kit={null} onSave={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /logo/i })).not.toBeInTheDocument();
    expect(screen.getByText(/save the kit first/i)).toBeInTheDocument();
  });

  it("uploads a logo once the kit exists", async () => {
    const onUploadLogo = vi.fn();
    render(<BrandKitForm kit={{ ...KIT, logo_url: null }} onSave={vi.fn()} onUploadLogo={onUploadLogo} />);
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "logo.png", { type: "image/png" }));
    expect(onUploadLogo).toHaveBeenCalledTimes(1);
  });

  it("only offers logo placement once there is a logo to place", () => {
    const { rerender } = render(<BrandKitForm kit={{ ...KIT, logo_url: null }} onSave={vi.fn()} />);
    expect(screen.queryByLabelText(/corner/i)).not.toBeInTheDocument();

    rerender(<BrandKitForm kit={KIT} onSave={vi.fn()} />);
    expect(screen.getByLabelText(/corner/i)).toHaveValue("bottom_right");
  });

  it("shows the chosen colours on a frame-shaped preview", async () => {
    render(<BrandKitForm kit={KIT} onSave={vi.fn()} />);
    // The brand name is drawn in the text colour, the slogan in the accent.
    const slogan = screen.getByText("La rentrée, en mieux");
    expect(slogan).toHaveStyle({ color: "#39E08B" });
  });

  it("keeps the preview in step while a colour is being changed", async () => {
    render(<BrandKitForm kit={KIT} onSave={vi.fn()} />);
    const hex = screen.getByLabelText(/accent hex/i);
    await userEvent.clear(hex);
    await userEvent.type(hex, "#FF0000");
    expect(screen.getByText("La rentrée, en mieux")).toHaveStyle({ color: "#FF0000" });
  });

  it("does not let the logo be scaled past a watermark", () => {
    render(<BrandKitForm kit={KIT} onSave={vi.fn()} />);
    // The server refuses above 0.35; the slider must not offer what will be rejected.
    expect(screen.getByLabelText(/^size$/i)).toHaveAttribute("max", "0.35");
  });
});

describe("BrandKitCard", () => {
  it("summarises the kit and can be selected", async () => {
    const onSelect = vi.fn();
    render(<BrandKitCard kit={KIT} onSelect={onSelect} />);
    expect(screen.getByText("Nova")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Nova"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("offers deletion by name so the confirmation cannot be ambiguous", async () => {
    const onDelete = vi.fn();
    render(<BrandKitCard kit={KIT} onSelect={vi.fn()} onDelete={onDelete} />);
    await userEvent.click(screen.getByRole("button", { name: /delete nova/i }));
    expect(onDelete).toHaveBeenCalled();
  });
});
