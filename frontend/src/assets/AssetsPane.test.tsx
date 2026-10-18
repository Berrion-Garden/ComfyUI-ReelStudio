import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { deleteAsset, importAssets, setAssetLabels, type AssetsData, type StudioView } from "../api";
import { AssetsPane } from "./AssetsPane";

vi.mock("../api", () => (
  { setAssetLabels: vi.fn(), deleteAsset: vi.fn(), importAssets: vi.fn() }));

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
    custom: [], themes: [], stills: [],
    backgrounds: [
      { path: "/ws/backgrounds/campus_sunset/bg_campus01_.png", slug: "bg_campus01",
        group: "backgrounds", labels: ["loc:campus_sunset", "background"],
        used_by: [], url: "/f/bg_campus.png" },
      { path: "/ws/backgrounds/court_sunset/bg_court01_.png", slug: "bg_court01",
        group: "backgrounds", labels: ["loc:court_sunset", "background"],
        used_by: [], url: "/f/bg_court.png" },
    ],
    sfx: [],
    audio: [
      { path: "/out/music_opening_1.wav", slug: "music_opening_1", group: "audio",
        labels: ["music", "track:opening"], used_by: [], url: "/f/m.wav" },
    ],
  },
};

const studio: StudioView = {
  title: "Test Studio", current: "ep1", saved: true, workspace: "/ws",
  scenes: [
    { slug: "ep1", title: "Episode 1", dir: "scenes/ep1", current: true,
      characters: ["fox_boy"], backgrounds: ["campus_sunset"] },
    { slug: "ep0", title: "Pilot", dir: "scenes/ep0", current: false,
      characters: ["tony", "unsorted"], backgrounds: [] },
  ],
};

function paneProps(over: Partial<Parameters<typeof AssetsPane>[0]> = {}) {
  return {
    assets: data, studio, selected: null, selectedPaths: new Set<string>(),
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

  it("sections collapse and stay collapsed across data refreshes", () => {
    const { rerender } = render(<AssetsPane {...paneProps()} />);
    const section = () =>
      screen.getByText("Characters").closest("details") as HTMLDetailsElement;
    expect(section().open).toBe(true);

    // the browser flips open before the toggle event reaches React
    section().open = false;
    fireEvent(section(), new Event("toggle", { bubbles: true }));
    expect(section().open).toBe(false);

    // the pane re-renders on every asset poll — the user's collapse sticks
    rerender(<AssetsPane {...paneProps()} />);
    expect(section().open).toBe(false);
  });

  it("backgrounds group into location pools like characters", () => {
    render(<AssetsPane {...paneProps()} />);
    expect(screen.getByText("campus_sunset")).toBeTruthy();
    expect(screen.getByText("court_sunset")).toBeTruthy();
    expect(screen.getByTestId("asset-backgrounds-bg_campus01")).toBeTruthy();
    expect(screen.getByTestId("asset-backgrounds-bg_court01")).toBeTruthy();
  });

  it("the Characters + panel imports another scene's pool into a named pool", () => {
    render(<AssetsPane {...paneProps()} />);

    // the + opens the panel with the OTHER scenes' pools
    fireEvent.click(screen.getByLabelText("upload into Characters"));
    fireEvent.click(screen.getByRole("button", { name: "Pilot · unsorted" }));

    // the target defaults to the source pool name; rename to merge into Amun
    const target = screen.getByLabelText("import target pool name");
    expect((target as HTMLInputElement).value).toBe("unsorted");
    fireEvent.change(target, { target: { value: "Amun" } });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(importAssets).toHaveBeenCalledWith({
      from: "ep0", characters: ["unsorted"], backgrounds: [], as: "Amun",
    });
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
