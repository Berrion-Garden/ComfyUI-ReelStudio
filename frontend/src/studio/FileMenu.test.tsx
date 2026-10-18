import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FileMenu } from "./FileMenu";
import { openScene, type StudioView } from "../api";

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
        characters: ["fox_boy"], backgrounds: ["campus.png"] },
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

  it("hides itself until the studio is fetched", () => {
    render(<FileMenu studio={null} onChanged={vi.fn()} busy={false} />);
    expect(screen.queryByText(/^File/)).toBeNull();
  });
});
