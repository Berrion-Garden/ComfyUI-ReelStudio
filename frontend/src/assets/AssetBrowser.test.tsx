import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { fetchAssets, setAssetLabels, type AssetsData } from "../api";
import { AssetBrowser } from "./AssetBrowser";

vi.mock("../api", () => ({ fetchAssets: vi.fn(), setAssetLabels: vi.fn() }));

const data: AssetsData = {
  groups: {
    characters: [
      { path: "/ws/characters/tony/face_.png", slug: "face", group: "characters",
        labels: ["char:tony"], used_by: [], url: "/f/face.png" },
    ],
    scenes: [], custom: [], backgrounds: [], themes: [], sfx: [],
    audio: [
      { path: "/out/music_opening_1.wav", slug: "music_opening_1", group: "audio",
        labels: ["music"], used_by: [], url: "/f/m.wav" },
    ],
  },
};

describe("AssetBrowser", () => {
  it("inspects the selected asset: large preview + label editor", async () => {
    vi.mocked(fetchAssets).mockResolvedValue(data);
    render(<AssetBrowser assets={data} selected={data.groups.characters[0]}
      onSelect={vi.fn()} onChanged={vi.fn()} />);

    const media = (await screen.findAllByAltText("face"))[0];
    expect(media.getAttribute("src")).toBe("/f/face.png");
    expect(screen.getByText("char:tony")).toBeTruthy();

    // adding a label writes through to the library
    vi.mocked(setAssetLabels).mockResolvedValue(undefined);
    fireEvent.change(screen.getByLabelText("new label for face"),
      { target: { value: "cond:were-tiger" } });
    fireEvent.submit(screen.getByLabelText("new label for face").closest("form")!);
    await waitFor(() =>
      expect(vi.mocked(setAssetLabels)).toHaveBeenCalledWith(
        "/ws/characters/tony/face_.png", ["char:tony", "cond:were-tiger"]));
  });

  it("renders audio assets with a player and picks from the grid", async () => {
    vi.mocked(fetchAssets).mockResolvedValue(data);
    const onSelect = vi.fn();
    render(<AssetBrowser assets={data} selected={null}
      onSelect={onSelect} onChanged={vi.fn()} />);

    await waitFor(() => expect(screen.getByTitle("face — char:tony")).toBeTruthy());
    expect(screen.getByTitle("music_opening_1 — music")).toBeTruthy();
    fireEvent.click(screen.getByTitle("face — char:tony"));
    expect(onSelect).toHaveBeenCalledWith(data.groups.characters[0]);
  });
});
