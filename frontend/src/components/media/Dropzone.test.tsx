/** Upload workflow tests (requirement 29). */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Dropzone } from "./Dropzone";

function imageFile(name = "photo.jpg", type = "image/jpeg", size = 1024) {
  const file = new File(["x".repeat(size)], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("Dropzone", () => {
  it("accepts images chosen through the file input", async () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, [imageFile("a.jpg"), imageFile("b.png", "image/png")]);

    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0]).toHaveLength(2);
  });

  it("rejects an unsupported type and explains why", async () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} />);

    // The file picker filters by `accept`, so a PDF can only arrive by drag and drop.
    const zone = screen.getByRole("button", { name: /drop your images here/i });
    fireEvent.drop(zone, {
      dataTransfer: { files: [imageFile("notes.pdf", "application/pdf")] },
    });

    expect(onFiles).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(/unsupported file type/i);
  });

  it("rejects a file over the size limit and names the limit", async () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} maxBytes={1000} />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, imageFile("big.jpg", "image/jpeg", 5000));

    expect(onFiles).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(/larger than/i);
  });

  it("accepts a drop", () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} />);

    const zone = screen.getByRole("button", { name: /drop your images here/i });
    fireEvent.drop(zone, { dataTransfer: { files: [imageFile()] } });

    expect(onFiles).toHaveBeenCalledTimes(1);
  });

  it("shows upload progress and blocks further input while uploading", () => {
    render(<Dropzone onFiles={vi.fn()} uploading progress={42} />);
    expect(screen.getByText(/uploading… 42%/i)).toBeInTheDocument();
    expect(document.querySelector("input[type=file]")).toBeDisabled();
  });

  it("only takes the first maxFiles files", async () => {
    const onFiles = vi.fn();
    render(<Dropzone onFiles={onFiles} maxFiles={2} />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, [imageFile("1.jpg"), imageFile("2.jpg"), imageFile("3.jpg")]);

    expect(onFiles.mock.calls[0][0]).toHaveLength(2);
    expect(screen.getByRole("alert")).toHaveTextContent(/first 2 files/i);
  });
});
