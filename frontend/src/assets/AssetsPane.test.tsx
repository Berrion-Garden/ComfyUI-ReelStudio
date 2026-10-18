import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { AssetsData } from "../api";
import { AssetsPane } from "./AssetsPane";

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
    custom: [], themes: [], backgrounds: [], stills: [],
    sfx: [],
    audio: [
      { path: "/out/music_opening_1.wav", slug: "music_opening_1", group: "audio",
        labels: ["music", "track:opening"], used_by: [], url: "/f/m.wav" },
    ],
  },
};

describe("AssetsPane", () => {
  it("groups assets and selects on click", () => {
    const onSelect = vi.fn();
    render(<AssetsPane assets={data} selected={null} onSelect={onSelect} />);

    // characters pool renders under its pool heading
    expect(screen.getByText("fox_boy")).toBeTruthy();
    const card = screen.getByTestId("asset-scenes-opening_still");
    expect(card.textContent).toContain("in 1 scene");
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith(data.groups.scenes[0]);
  });

  it("arrow keys walk the flat asset order", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<AssetsPane assets={data} selected={null} onSelect={onSelect} />);
    expect(screen.getByTestId("asset-characters-sit")).toBeTruthy();

    const pane = screen.getByTestId("assets-pane");
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith(data.groups.characters[0]);

    // with the first asset selected, ArrowDown moves to the next in order
    rerender(<AssetsPane assets={data} selected={data.groups.characters[0]} onSelect={onSelect} />);
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith(data.groups.characters[1]);
    fireEvent.keyDown(pane, { key: "ArrowUp" });
    expect(onSelect).toHaveBeenLastCalledWith(data.groups.characters[0]);
  });
});
