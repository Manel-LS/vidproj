/**
 * Character Studio form.
 *
 * The behaviour worth pinning is the description: it is the sentence replayed
 * verbatim into every image prompt, so the form has to show what is actually being
 * sent and let a hand-written one win over the assembled version.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Character } from "@/lib/api/types";
import { CharacterCard, CharacterForm } from "./CharacterForm";

const SKANDER: Character = {
  id: "char-1",
  name: "Skander",
  kind: "baby",
  age: "2 years old",
  gender: "boy",
  skin_tone: "olive skin",
  hair: "short curly black hair",
  clothes: "a red velvet jebba",
  headwear: "a red chechia",
  expression: "a wide mischievous smile",
  personality: "cheeky",
  environment: "a sunlit Tunisian courtyard",
  description:
    "adorable realistic toddler, 2 years old, boy, olive skin, short curly black hair, wearing a red velvet jebba, with a red chechia, a wide mischievous smile, in a sunlit Tunisian courtyard",
  reference_media_id: null,
  reference_image_url: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("CharacterForm", () => {
  it("will not save a character with no name", async () => {
    const onSave = vi.fn();
    render(<CharacterForm character={null} onSave={onSave} />);
    expect(screen.getByRole("button", { name: /create character/i })).toBeDisabled();
  });

  it("sends what was typed", async () => {
    const onSave = vi.fn();
    render(<CharacterForm character={null} onSave={onSave} />);

    await userEvent.type(screen.getByLabelText(/^name$/i), "Skander");
    await userEvent.type(screen.getByLabelText(/headwear/i), "a red chechia");
    await userEvent.click(screen.getByRole("button", { name: /create character/i }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toMatchObject({
      name: "Skander",
      headwear: "a red chechia",
    });
  });

  it("shows the exact clause the image provider receives", () => {
    render(<CharacterForm character={SKANDER} onSave={vi.fn()} />);
    // "the same ..." is the instruction that tells the model this is a returning
    // subject; showing it is how the user can tell why a face drifted.
    expect(screen.getByText(new RegExp(`the same ${SKANDER.description.slice(0, 40)}`))).toBeInTheDocument();
  });

  it("keeps a hand-written description instead of the assembled one", async () => {
    const onSave = vi.fn();
    render(<CharacterForm character={SKANDER} onSave={onSave} />);

    const field = screen.getByLabelText(/^description$/i);
    await userEvent.clear(field);
    await userEvent.type(field, "a stubborn goat in a waistcoat");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(onSave.mock.calls[0][0].description).toBe("a stubborn goat in a waistcoat");
  });

  it("waits for a saved character before offering a reference image", () => {
    render(<CharacterForm character={null} onSave={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /reference/i })).not.toBeInTheDocument();
    expect(screen.getByText(/save the character first/i)).toBeInTheDocument();
  });

  it("uploads a reference image once the character exists", async () => {
    const onUploadReference = vi.fn();
    render(
      <CharacterForm character={SKANDER} onSave={vi.fn()} onUploadReference={onUploadReference} />,
    );
    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "face.jpg", { type: "image/jpeg" }));
    expect(onUploadReference).toHaveBeenCalledTimes(1);
  });
});

describe("CharacterCard", () => {
  it("summarises the character and can be selected", async () => {
    const onSelect = vi.fn();
    render(<CharacterCard character={SKANDER} onSelect={onSelect} />);
    expect(screen.getByText("Skander")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Skander"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("offers deletion by name, so the confirm dialog cannot be ambiguous", async () => {
    const onDelete = vi.fn();
    render(<CharacterCard character={SKANDER} onSelect={vi.fn()} onDelete={onDelete} />);
    await userEvent.click(screen.getByRole("button", { name: /delete skander/i }));
    expect(onDelete).toHaveBeenCalled();
  });
});
