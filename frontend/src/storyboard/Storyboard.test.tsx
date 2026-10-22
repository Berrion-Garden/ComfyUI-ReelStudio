// The Storyboard stage view: sections, pen-icon editing, chip navigation.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Storyboard } from "./Storyboard";
import type { NarrativeView } from "../api";
import type { ProjectView } from "../types";

vi.mock("../api", () => ({
  fetchNarrative: vi.fn(),
  saveNarrative: vi.fn(),
}));

import { fetchNarrative, saveNarrative } from "../api";

const NARRATIVE: NarrativeView = {
  path: "/w/storyboard.yaml",
  doc: {
    style: "Cinematic anime",
    acts: [{
      title: "Act 1 — Waking Up",
      music: "guitar riff",
      checkpoints: [{
        title: "Scene 1 — The Antique Shop",
        characters: ["amunrekh"],
        locations: ["antique_shop"],
        shots: [{
          title: "1.1 Establishing Shot",
          text: "Establishing shot of the shop at dawn.",
        }],
      }],
    }],
  },
};

function project(): ProjectView {
  return {
    yaml_path: "/w/reel.yaml", fps: 24, width: 100, height: 100,
    total_s: 5, final_path: null, flags: {}, sfx_volume: [],
    scenes: [{
      id: "s1_shop", next: null, index: 0, mode: "i2v", frames: 22,
      duration_s: 0.9, first: { kind: "none" }, last: { kind: "none" },
      description: "The shop at dawn.", has_freeze: false, has_bell: false,
      bell_at: null, has_sfx: false, video_url: null, stale: false,
      start_s: 0,
    }],
    music: [], overlays: [], final_url: null, jobs: [],
    characters: {
      amunrekh: { attributes: { bandages: "papyrus linen" } },
    },
    location_blocks: {
      antique_shop: { pro: "A dimly lit antique store at dawn." },
    },
  };
}

beforeEach(() => {
  vi.mocked(fetchNarrative).mockResolvedValue(NARRATIVE);
  vi.mocked(saveNarrative).mockResolvedValue();
});

describe("Storyboard", () => {
  it("renders acts and checkpoints from the fetched doc", async () => {
    render(<Storyboard project={project()} refreshTick={0} />);
    await screen.findByText("Act 1 — Waking Up");
    expect(screen.getByText("Scene 1 — The Antique Shop")).toBeTruthy();
    expect(screen.getByText(/Establishing shot/)).toBeTruthy();
  });

  it("the pen opens an inline edit and Save PUTs the whole doc", async () => {
    render(<Storyboard project={project()} refreshTick={0} />);
    await screen.findByText("Scene 1 — The Antique Shop");

    fireEvent.click(screen.getByLabelText("edit 1.1 Establishing Shot"));
    const area = screen.getByLabelText("Text");
    fireEvent.change(area, { target: { value: "Establishing shot, revised." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(saveNarrative).toHaveBeenCalled());
    const doc = vi.mocked(saveNarrative).mock.calls[0][0];
    expect(doc.acts[0].checkpoints[0].shots[0].text)
      .toBe("Establishing shot, revised.");
  });

  it("a character chip navigates to the Characters section, focused", async () => {
    render(<Storyboard project={project()} refreshTick={0} />);
    await screen.findByText("Scene 1 — The Antique Shop");

    fireEvent.click(screen.getByRole("button", { name: "amunrekh" }));
    expect(await screen.findByText("bandages")).toBeTruthy();
    // the character card carries the focus highlight
    const card = screen.getByText("amunrekh").closest("article");
    expect(card?.className).toContain("focused");
  });

  it("the section switch shows this project's scenes", async () => {
    render(<Storyboard project={project()} refreshTick={0} />);
    await screen.findByText("Scene 1 — The Antique Shop");
    fireEvent.click(screen.getByRole("button", { name: "Scenes" }));
    expect(await screen.findByText("The shop at dawn.")).toBeTruthy();
  });
});
