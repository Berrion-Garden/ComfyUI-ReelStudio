import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { fetchAssets, type AssetsData } from "../api";
import { AssetsPane } from "./AssetsPane";

vi.mock("../api", () => ({ fetchAssets: vi.fn() }));

const data: AssetsData = {
  groups: {
    characters: [
      { path: "/ws/characters/fox_boy/sit_.png", slug: "sit", group: "characters",
        labels: ["char:fox_boy", "pose:sit"], used_by: [], url: "/f/sit.png" },
      { path: "/ws/characters/fox_boy/run_.png", slug: "run", group: "characters",
        labels: ["char:fox_boy", "pose:run"], used_by: [], url: "/f/run.png" },
    ],
    scenes: [
      { path: "/stills/opening_still_.png", slug: "opening_still", group: "scenes",
        labels: ["still:opening"], used_by: ["s1_ramen"], url: "/f/opening.png" },
    ],
    custom: [], themes: [],
    sfx: [],
    audio: [
      { path: "/out/music_opening_1.wav", slug: "music_opening_1", group: "audio",
        labels: ["music", "track:opening"], used_by: [], url: "/f/m.wav" },
    ],
  },
};

describe("AssetsPane", () => {
  it("groups assets and selects on click", async () => {
    vi.mocked(fetchAssets).mockResolvedValue(data);
    const onSelect = vi.fn();
    render(<AssetsPane selected={null} onSelect={onSelect} />);

    await waitFor(() => expect(screen.getByTestId("assets-pane")).toBeTruthy());
    // characters pool renders under its pool heading
    expect(screen.getByText("fox_boy")).toBeTruthy();
    const card = screen.getByTestId("asset-scenes-opening_still");
    expect(card.textContent).toContain("in 1 scene");
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith({ url: "/f/opening.png", name: "opening_still" });
  });

  it("arrow keys walk the flat asset order", async () => {
    vi.mocked(fetchAssets).mockResolvedValue(data);
    const onSelect = vi.fn();
    const { rerender } = render(<AssetsPane selected={null} onSelect={onSelect} />);
    await waitFor(() => expect(screen.getByTestId("asset-characters-sit")).toBeTruthy());

    const pane = screen.getByTestId("assets-pane");
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith({ url: "/f/sit.png", name: "sit" });

    // with the first asset selected, ArrowDown moves to the next in order
    rerender(<AssetsPane selected={{ url: "/f/sit.png", name: "sit" }} onSelect={onSelect} />);
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith({ url: "/f/run.png", name: "run" });
    fireEvent.keyDown(pane, { key: "ArrowUp" });
    expect(onSelect).toHaveBeenLastCalledWith({ url: "/f/sit.png", name: "sit" });
  });
});
