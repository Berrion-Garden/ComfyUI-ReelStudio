// The Storyboard stage view: sections, pen-icon editing, chip navigation.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Storyboard } from "./Storyboard";
import type { NarrativeView } from "../api";
import type { ProjectView } from "../types";

vi.mock("../api", () => ({
  fetchNarrative: vi.fn(),
  saveNarrative: vi.fn(),
  saveBlock: vi.fn(),
  API: "/api",
}));

import { fetchNarrative, saveBlock, saveNarrative } from "../api";

const NARRATIVE: NarrativeView = {
  path: "/w/storyboard.yaml",
  doc: {
    style: "Cinematic anime",
    acts: [{
      title: "Act 1 — Waking Up",
      music: "guitar riff",
      checkpoints: [{
      id: "scene-1",
      title: "Scene 1 — The Antique Shop",
      characters: ["amunrekh"],
      locations: ["antique_shop"],
      shots: [{
        id: "1.1",
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
      description: "The shop at dawn.", beat: "1.1", prompt: "composed prompt",
      has_freeze: false, has_bell: false,
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
    render(<Storyboard project={project()} refreshTick={0}
  onChanged={() => {}} />);
    await screen.findByText("Act 1 — Waking Up");
    expect(screen.getByText("Scene 1 — The Antique Shop")).toBeTruthy();
    expect(screen.getByText(/Establishing shot/)).toBeTruthy();
    // the derived beat id shows on the scene card — what reel.yaml wires to
    expect(screen.getByText("scene-1")).toBeTruthy();
  });

  it("the pen opens an inline edit and Save PUTs the whole doc", async () => {
    render(<Storyboard project={project()} refreshTick={0}
  onChanged={() => {}} />);
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
    render(<Storyboard project={project()} refreshTick={0}
  onChanged={() => {}} />);
    await screen.findByText("Scene 1 — The Antique Shop");

    fireEvent.click(screen.getByRole("button", { name: "amunrekh" }));
    expect(await screen.findByText("bandages")).toBeTruthy();
    // the character card carries the focus highlight
    const card = screen.getByText("amunrekh").closest("article");
    expect(card?.className).toContain("focused");
  });

  it("the section switch shows this project's scenes", async () => {
    render(<Storyboard project={project()} refreshTick={0}
  onChanged={() => {}} />);
    await screen.findByText("Scene 1 — The Antique Shop");
    fireEvent.click(screen.getByRole("button", { name: "Scenes" }));
    // the scene card shows the COMPOSED prompt and the anchor stills
    expect(await screen.findByText("composed prompt")).toBeTruthy();
    expect(screen.getByText("first: none")).toBeTruthy();
    expect(screen.getByText("last: none")).toBeTruthy();
  });

  it("the scene card's pen opens the owning beat's editor in Narrative",
    async () => {
      render(<Storyboard project={project()} refreshTick={0}
        onChanged={() => {}} />);
      await screen.findByText("Scene 1 — The Antique Shop");
      fireEvent.click(screen.getByRole("button", { name: "Scenes" }));
      fireEvent.click(screen.getByRole("button", { name: /edit action text/ }));

      // back in the narrative, the shot editor is open on the wired beat
      const area = await screen.findByLabelText("Text");
      expect((area as HTMLTextAreaElement).value)
        .toBe("Establishing shot of the shop at dawn.");
      fireEvent.change(area, { target: { value: "revised action" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
      await waitFor(() => expect(saveNarrative).toHaveBeenCalled());
    });

  it("a character attribute's pen writes the block through PUT /api/block",
    async () => {
      render(<Storyboard project={project()} refreshTick={0}
        onChanged={() => {}} />);
      await screen.findByText("Scene 1 — The Antique Shop");
      fireEvent.click(screen.getByRole("button", { name: "amunrekh" }));
      fireEvent.click(await screen.findByTitle("edit bandages"));
      const area = screen.getByRole("textbox");
      fireEvent.change(area, { target: { value: "papyrus linen, aged" } });
      fireEvent.click(screen.getByRole("button", { name: "Save" }));

      await waitFor(() => expect(saveBlock).toHaveBeenCalled());
      const [section, slug, block] = vi.mocked(saveBlock).mock.calls[0];
      expect(section).toBe("characters");
      expect(slug).toBe("amunrekh");
      expect((block as { attributes: Record<string, string> })
        .attributes.bandages).toBe("papyrus linen, aged");
    });
});
