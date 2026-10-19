import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { deleteAsset, getProvenance, setAssetLabels, type AssetsData } from "../api";
import { AssetBrowser } from "./AssetBrowser";

vi.mock("../api", () => ({
  setAssetLabels: vi.fn(), deleteAsset: vi.fn(), getProvenance: vi.fn(),
}));
// the inspector's provenance fetch must resolve to "nothing known" by default
vi.mocked(getProvenance).mockResolvedValue(
  { file: "", job: null, record: null, embedded: null });

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

function browserProps(over: Partial<Parameters<typeof AssetBrowser>[0]> = {}) {
  return {
    assets: data, selected: null, selectedList: [],
    onSelect: vi.fn(), onPrimary: vi.fn(), onChanged: vi.fn(), ...over,
  };
}

describe("AssetBrowser", () => {
  it("shows the single selected asset, large, with its label editor", async () => {
    render(<AssetBrowser {...browserProps(
      { selected: data.groups.characters[0] })} />);

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
    render(<AssetBrowser {...browserProps(
      { selected: data.groups.stills[0], onSelect })} />);

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
    render(<AssetBrowser {...browserProps(
      { selected: data.groups.stills[0], onSelect })} />);

    vi.mocked(deleteAsset).mockResolvedValue(undefined);
    fireEvent.click(screen.getByLabelText("delete tony_dunk01"));
    await waitFor(() => expect(vi.mocked(deleteAsset)).toHaveBeenCalledWith(
      "/out/tony_dunk01_00001_.png"));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(null));
  });

  it("nothing selected: an empty hint, no inspector", () => {
    render(<AssetBrowser {...browserProps()} />);
    expect(screen.getByTestId("asset-stage").textContent)
      .toContain("select an asset");
  });

  it("the provenance block claws back job, seed and prompt", async () => {
    vi.mocked(getProvenance).mockResolvedValue({
      file: "/out/tony_dunk01_00001_.png", job: "abc123",
      record: { id: "abc123", kind: "image_edit", target: "tony_dunk",
                args: { kind: "image_edit", name: "tony_dunk" },
                status: "done", ts: 1 },
      embedded: { prompt: "a were-tiger mid-dunk", seed: 42, steps: 8 },
    });
    render(<AssetBrowser {...browserProps(
      { selected: data.groups.stills[0] })} />);

    await screen.findByTestId("inspector-provenance");
    const toggle = screen.getByRole("button", { name: /provenance/ });
    expect(toggle.textContent).toBe("▸ provenance · job abc123");
    fireEvent.click(toggle);
    expect(await screen.findByText("a were-tiger mid-dunk")).toBeTruthy();
    const block = screen.getByTestId("inspector-provenance").textContent!;
    expect(block).toContain("seed");
    expect(block).toContain("image_edit tony_dunk");
  });

  it("a multi-selection turns the display into a carousel", () => {
    const picked = [data.groups.characters[0], data.groups.stills[0]];
    const onPrimary = vi.fn();
    const { rerender } = render(<AssetBrowser {...browserProps(
      { selected: picked[1], selectedList: picked, onPrimary })} />);

    expect(screen.getByText("2 / 2")).toBeTruthy();
    // › wraps to the other picked asset, keeping the selection intact
    fireEvent.click(screen.getByLabelText("next picked asset"));
    expect(onPrimary).toHaveBeenCalledWith(picked[0]);
    fireEvent.click(screen.getByLabelText("previous picked asset"));
    expect(onPrimary).toHaveBeenCalledWith(picked[0]);
    // « and » jump to the ends of the picked list
    fireEvent.click(screen.getByLabelText("last picked asset"));
    expect(onPrimary).toHaveBeenCalledWith(picked[1]);
    fireEvent.click(screen.getByLabelText("first picked asset"));
    expect(onPrimary).toHaveBeenCalledWith(picked[0]);

    // a single selection shows no carousel chrome
    rerender(<AssetBrowser {...browserProps(
      { selected: picked[0], selectedList: [picked[0]], onPrimary })} />);
    expect(screen.queryByLabelText("next picked asset")).toBeNull();
  });
});
