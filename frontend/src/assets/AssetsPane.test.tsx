import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { deleteAsset, setAssetLabels, type AssetsData } from "../api";
import { AssetsPane } from "./AssetsPane";

vi.mock("../api", () => (
  { setAssetLabels: vi.fn(), deleteAsset: vi.fn() }));

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
      { path: "/out/dunk01_.png", slug: "dunk01", group: "scenes",
        labels: ["char:tony", "non-verified"], used_by: [], url: "/f/dunk.png" },
    ],
    custom: [], themes: [], backgrounds: [], stills: [],
    sfx: [],
    audio: [
      { path: "/out/music_opening_1.wav", slug: "music_opening_1", group: "audio",
        labels: ["music", "track:opening"], used_by: [], url: "/f/m.wav" },
    ],
  },
};

function paneProps(over: Partial<Parameters<typeof AssetsPane>[0]> = {}) {
  return {
    assets: data, selected: null, selectedPaths: new Set<string>(),
    onSelect: vi.fn(), onChanged: vi.fn(), ...over,
  };
}

describe("AssetsPane", () => {
  it("groups assets and selects on click", () => {
    const onSelect = vi.fn();
    render(<AssetsPane {...paneProps({ onSelect })} />);

    // characters pool renders under its pool heading
    expect(screen.getByText("fox_boy")).toBeTruthy();
    const card = screen.getByTestId("asset-scenes-opening_still");
    expect(card.textContent).toContain("in 1 scene");
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith(data.groups.scenes[0], false);
  });

  it("shift-click adds to the multi-selection", () => {
    const onSelect = vi.fn();
    render(<AssetsPane {...paneProps({ onSelect })} />);
    fireEvent.click(screen.getByTestId("asset-characters-sit"), { shiftKey: true });
    expect(onSelect).toHaveBeenCalledWith(data.groups.characters[0], true);
  });

  it("arrow keys walk the flat asset order", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<AssetsPane {...paneProps({ onSelect })} />);
    expect(screen.getByTestId("asset-characters-sit")).toBeTruthy();

    const pane = screen.getByTestId("assets-pane");
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith(data.groups.characters[0]);

    // with the first asset selected, ArrowDown moves to the next in order
    rerender(<AssetsPane {...paneProps(
      { onSelect, selected: data.groups.characters[0] })} />);
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith(data.groups.characters[1]);
    fireEvent.keyDown(pane, { key: "ArrowUp" });
    expect(onSelect).toHaveBeenLastCalledWith(data.groups.characters[0]);
  });

  it("unaccepted thumbnails carry their own check and x", async () => {
    render(<AssetsPane {...paneProps()} />);
    const ok = screen.getByLabelText("accept dunk01");
    const del = screen.getByLabelText("delete dunk01");
    vi.mocked(setAssetLabels).mockResolvedValue(undefined);
    fireEvent.click(ok);
    await Promise.resolve();
    expect(vi.mocked(setAssetLabels)).toHaveBeenCalledWith(
      "/out/dunk01_.png", ["char:tony"]);

    // verified assets carry no inline controls
    expect(screen.queryByLabelText("accept opening_still")).toBeNull();

    vi.mocked(deleteAsset).mockResolvedValue(undefined);
    fireEvent.click(del);
    await Promise.resolve();
    expect(vi.mocked(deleteAsset)).toHaveBeenCalledWith("/out/dunk01_.png");
  });

  it("the ... menu copies an asset:<path> reference and offers delete", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<AssetsPane {...paneProps()} />);

    fireEvent.click(screen.getByLabelText("actions for opening_still"));
    fireEvent.click(screen.getByText("Copy reference"));
    await Promise.resolve();
    expect(writeText).toHaveBeenCalledWith("asset:/stills/opening_still_.png");
  });
});
