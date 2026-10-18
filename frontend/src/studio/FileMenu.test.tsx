import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FileMenu } from "./FileMenu";
import { newScene, openScene, type StudioView } from "../api";

vi.mock("../api", () => ({
  openScene: vi.fn(),
  saveScene: vi.fn(),
  newScene: vi.fn(),
}));

function studio(partial: Partial<StudioView> = {}): StudioView {
  return {
    title: "Anime Fantasy",
    current: "ep1",
    saved: true,
    workspace: "/w/scenes/ep1",
    scenes: [
      { slug: "ep1", title: "Episode 1", dir: "scenes/ep1", current: true,
        characters: ["fox_boy"], backgrounds: ["campus_sunset"] },
      { slug: "ep2", title: "Episode 2", dir: "scenes/ep2", current: false,
        characters: [], backgrounds: [] },
    ],
    ...partial,
  };
}

describe("FileMenu", () => {
  it("offers save, open, and new scene", async () => {
    const onChanged = vi.fn();
    render(<FileMenu studio={studio()} onChanged={onChanged} busy={false} />);
    fireEvent.click(screen.getByText(/^File/));
    expect(screen.getByText(/Save scene/)).toBeTruthy();
    expect(screen.getByText(/Episode 2/)).toBeTruthy();
    expect(screen.getByText(/New scene…/)).toBeTruthy();
  });

  it("opens another scene through the API", async () => {
    const onChanged = vi.fn(async () => {});
    vi.mocked(openScene).mockResolvedValue(studio({ current: "ep2" }));
    render(<FileMenu studio={studio()} onChanged={onChanged} busy={false} />);
    fireEvent.click(screen.getByText(/^File/));
    fireEvent.click(screen.getByText(/Episode 2/));
    await waitFor(() => expect(openScene).toHaveBeenCalledWith("ep2"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("creates a scene from the name alone — the slug derives server-side", async () => {
    vi.mocked(newScene).mockResolvedValue(studio());
    render(<FileMenu studio={studio()} onChanged={vi.fn()} busy={false} />);
    fireEvent.click(screen.getByText(/^File/));
    fireEvent.click(screen.getByText(/New scene…/));
    fireEvent.change(screen.getByPlaceholderText("Episode 2"),
      { target: { value: "Amun's Reveal" } });
    const create = screen.getByText("Create scene") as HTMLButtonElement;
    expect(create.disabled).toBe(false);
    fireEvent.click(create);
    await waitFor(() =>
      expect(newScene).toHaveBeenCalledWith("Amun's Reveal", undefined));
  });

  it("importing pools is opt-in and rides the create call", async () => {
    vi.mocked(newScene).mockResolvedValue(studio());
    render(<FileMenu studio={studio()} onChanged={vi.fn()} busy={false} />);
    fireEvent.click(screen.getByText(/^File/));
    fireEvent.click(screen.getByText(/New scene…/));

    // off by default: no picker is shown, create carries no import spec
    expect(screen.queryByText("fox_boy")).toBeNull();
    fireEvent.change(screen.getByPlaceholderText("Episode 2"),
      { target: { value: "Episode 3" } });
    fireEvent.click(screen.getByText("Create scene"));
    await waitFor(() =>
      expect(newScene).toHaveBeenCalledWith("Episode 3", undefined));
  });

  it("the import toggle reveals the pools of the chosen source scene", async () => {
    vi.mocked(newScene).mockResolvedValue(studio());
    render(<FileMenu studio={studio()} onChanged={vi.fn()} busy={false} />);
    fireEvent.click(screen.getByText(/^File/));
    fireEvent.click(screen.getByText(/New scene…/));
    fireEvent.click(screen.getByLabelText("bring in characters & locations"));

    fireEvent.click(screen.getByRole("button", { name: "fox_boy" }));
    fireEvent.click(screen.getByRole("button", { name: "campus_sunset" }));
    fireEvent.change(screen.getByPlaceholderText("Episode 2"),
      { target: { value: "Episode 3" } });
    fireEvent.click(screen.getByText("Create scene"));
    await waitFor(() => expect(newScene).toHaveBeenCalledWith("Episode 3", {
      from: "ep1", characters: ["fox_boy"], backgrounds: ["campus_sunset"],
    }));
  });

  it("Create stays disabled with no name", () => {
    render(<FileMenu studio={studio()} onChanged={vi.fn()} busy={false} />);
    fireEvent.click(screen.getByText(/^File/));
    fireEvent.click(screen.getByText(/New scene…/));
    expect((screen.getByText("Create scene") as HTMLButtonElement).disabled)
      .toBe(true);
  });

  it("hides itself until the studio is fetched", () => {
    render(<FileMenu studio={null} onChanged={vi.fn()} busy={false} />);
    expect(screen.queryByText(/^File/)).toBeNull();
  });
});
