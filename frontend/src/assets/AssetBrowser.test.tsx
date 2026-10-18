import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { deleteAsset, setAssetLabels, type AssetsData } from "../api";
import { AssetBrowser } from "./AssetBrowser";

vi.mock("../api", () => (
  { setAssetLabels: vi.fn(), deleteAsset: vi.fn() }));

const data: AssetsData = {
  groups: {
    characters: [
      { path: "/ws/characters/tony/face_.png", slug: "face", group: "characters",
        labels: ["char:tony"], used_by: [], url: "/f/face.png" },
    ],
    scenes: [], custom: [], backgrounds: [], themes: [], sfx: [], audio: [],
    stills: [
      { path: "/out/tony_dunk01_00001_.png", slug: "tony_dunk01", group: "stills",
        labels: ["char:tony", "shot:tony_dunk", "non-verified"], used_by: [],
        url: "/f/dunk.png" },
    ],
  },
};

describe("AssetBrowser", () => {
  it("shows the single selected asset, large, with its label editor", async () => {
    render(<AssetBrowser assets={data} selected={data.groups.characters[0]}
      onSelect={vi.fn()} onChanged={vi.fn()} />);

    const media = await screen.findByAltText("face");
    expect(media.getAttribute("src")).toBe("/f/face.png");
    expect(screen.getByText("char:tony")).toBeTruthy();
    expect(screen.queryByLabelText("verify face")).toBeNull(); // already verified

    // adding a label writes through to the library
    vi.mocked(setAssetLabels).mockResolvedValue(undefined);
    fireEvent.change(screen.getByLabelText("new label for face"),
      { target: { value: "cond:were-tiger" } });
    fireEvent.submit(screen.getByLabelText("new label for face").closest("form")!);
    await waitFor(() =>
      expect(vi.mocked(setAssetLabels)).toHaveBeenCalledWith(
        "/ws/characters/tony/face_.png", ["char:tony", "cond:were-tiger"]));
  });

  it("non-verified assets get a check (approve) and an x (delete)", async () => {
    const onSelect = vi.fn();
    render(<AssetBrowser assets={data} selected={data.groups.stills[0]}
      onSelect={onSelect} onChanged={vi.fn()} />);

    // ✓ removes only the non-verified label — and with it, the buttons
    vi.mocked(setAssetLabels).mockResolvedValue(undefined);
    fireEvent.click(screen.getByLabelText("verify tony_dunk01"));
    await waitFor(() =>
      expect(vi.mocked(setAssetLabels)).toHaveBeenCalledWith(
        "/out/tony_dunk01_00001_.png", ["char:tony", "shot:tony_dunk"]));
    await waitFor(() =>
      expect(screen.queryByLabelText("delete tony_dunk01")).toBeNull());
  });

  it("✕ on a non-verified asset deletes the file and deselects", async () => {
    const onSelect = vi.fn();
    render(<AssetBrowser assets={data} selected={data.groups.stills[0]}
      onSelect={onSelect} onChanged={vi.fn()} />);

    vi.mocked(deleteAsset).mockResolvedValue(undefined);
    fireEvent.click(screen.getByLabelText("delete tony_dunk01"));
    await waitFor(() => expect(vi.mocked(deleteAsset)).toHaveBeenCalledWith(
      "/out/tony_dunk01_00001_.png"));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(null));
  });

  it("nothing selected: an empty hint, no inspector", () => {
    render(<AssetBrowser assets={data} selected={null}
      onSelect={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.getByTestId("asset-stage").textContent)
      .toContain("select an asset");
  });
});
