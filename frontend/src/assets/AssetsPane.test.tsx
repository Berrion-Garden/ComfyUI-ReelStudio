import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { deleteAsset, importAssets, setAssetLabels, type AssetsData, type StudioView } from "../api";
import { AssetsPane } from "./AssetsPane";

vi.mock("../api", () => (
  { setAssetLabels: vi.fn(), deleteAsset: vi.fn(), importAssets: vi.fn() }));

const data: AssetsData = {
  groups: {
    characters: [
      { path: "/ws/characters/fox_boy/references/base.webp", slug: "base", group: "characters",
        labels: ["char:fox_boy", "pose:base", "reference"], used_by: [], url: "/f/base.png" },
      { path: "/ws/characters/fox_boy/posed_stills/fox_boy_ref01.png", slug: "fox_boy_ref01",
        group: "characters",
        labels: ["char:fox_boy", "pose:fox_boy_ref01", "posed", "non-verified"],
        used_by: [], url: "/f/fox_boy_ref01.png" },
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
    fireEvent.click(screen.getByTestId("asset-characters-base"), { shiftKey: true });
    expect(onSelect).toHaveBeenCalledWith(data.groups.characters[0], true);
  });

  it("arrow keys walk the flat asset order", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<AssetsPane {...paneProps({ onSelect })} />);
    expect(screen.getByTestId("asset-characters-base")).toBeTruthy();

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

    // verified assets carry no accept control — but the delete ✕ stays
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

  it("character pools split into reference and posed stills, each collapsible", () => {
    const { rerender } = render(<AssetsPane {...paneProps()} />);
    expect(screen.getByTestId("asset-characters-base")).toBeTruthy();
    expect(screen.getByTestId("asset-characters-fox_boy_ref01")).toBeTruthy();

    const refSub = () =>
      screen.getByText("reference").closest("details") as HTMLDetailsElement;
    const posedSub = () =>
      screen.getByText("posed stills").closest("details") as HTMLDetailsElement;
    expect(refSub().open).toBe(true);
    expect(posedSub().open).toBe(true);

    // collapse the reference side — the periodic refresh keeps it collapsed
    refSub().open = false;
    fireEvent(refSub(), new Event("toggle", { bubbles: false }));
    rerender(<AssetsPane {...paneProps()} />);
    expect(refSub().open).toBe(false);
    expect(posedSub().open).toBe(true);
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
    await screen.findByText("copied ✓");
    expect(writeText).toHaveBeenCalledWith("asset:/stills/opening_still_.png");

    // Delete goes straight to the API — any asset, verified or not
    fireEvent.click(screen.getByLabelText("actions for dunk01"));
    fireEvent.click(screen.getByText("Delete"));
    expect(deleteAsset).toHaveBeenCalledWith("/out/dunk01_.png");
  });

  it("every asset card carries the delete ✕, verified or not", () => {
    render(<AssetsPane {...paneProps()} />);
    // verified, unverified, character reference and audio alike
    expect(screen.getByLabelText("delete opening_still")).toBeTruthy();
    expect(screen.getByLabelText("delete dunk01")).toBeTruthy();
    expect(screen.getByLabelText("delete base")).toBeTruthy();
    expect(screen.getByLabelText("delete music_opening_1")).toBeTruthy();
  });

  it("a refused delete shows the server's message in the error banner", async () => {
    vi.mocked(deleteAsset).mockRejectedValue(
      new Error("tied to scene start/end: s1_ramen"));
    render(<AssetsPane {...paneProps()} />);

    fireEvent.click(screen.getByLabelText("delete opening_still"));
    await screen.findByText(/tied to scene start\/end: s1_ramen/);
    const banner = document.querySelector(".assets-error");
    expect(banner?.textContent).toContain("tied to scene start/end: s1_ramen");
  });

  it("copy falls back to execCommand on insecure origins", async () => {
    // plain-http LAN origins have no navigator.clipboard at all
    Object.assign(navigator, { clipboard: undefined });
    const exec = vi.fn(() => true);
    document.execCommand = exec as unknown as typeof document.execCommand;
    render(<AssetsPane {...paneProps()} />);

    fireEvent.click(screen.getByLabelText("actions for opening_still"));
    fireEvent.click(screen.getByText("Copy reference"));
    await screen.findByText("copied ✓");
    expect(exec).toHaveBeenCalled();
  });
});
