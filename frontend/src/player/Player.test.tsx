import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Player } from "./Player";
import type { SceneView } from "../types";

function scene(partial: Partial<SceneView>): SceneView {
  return {
    id: "s1", next: null, index: 0, mode: "i2v", frames: 107,
    duration_s: 4.5, start_s: 0,
    first: { kind: "none" }, last: { kind: "none" },
    description: "", has_freeze: false, has_bell: false, has_sfx: false,
    video_url: null, stale: false,
    ...partial,
  };
}

describe("Player", () => {
  it("renders the empty state before any scene renders", () => {
    render(<Player scenes={[scene({})]} />);
    expect(screen.getByText(/No renders yet/)).toBeTruthy();
  });

  it("the asset toggle appears with a selection and swaps the stage", () => {
    render(
      <Player
        scenes={[scene({ id: "s1", video_url: "/v.mp4" })]}
        selectedAsset={{ url: "/f/still.png", name: "still" }}
      />,
    );
    const toggle = screen.getByTitle("show still");
    expect(toggle.textContent).toBe("🖼 asset");
    fireEvent.click(toggle);
    // the stage now shows the image, the overlay is hidden
    const stage = screen.getByTestId("player").querySelector(".player-stage")!;
    expect(stage.querySelector("img.active")).toBeTruthy();
    expect(stage.querySelector("img.active")!.getAttribute("src")).toBe("/f/still.png");
    expect(screen.getByTitle("back to the video")).toBeTruthy();
  });
});
