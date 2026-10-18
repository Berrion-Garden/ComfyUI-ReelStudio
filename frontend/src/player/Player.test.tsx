import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Player } from "./Player";
import type { SceneView } from "../types";

function scene(partial: Partial<SceneView>): SceneView {
  return {
    id: "s1", next: null, index: 0, mode: "i2v", frames: 107,
    duration_s: 4.5, start_s: 0,
    first: { kind: "none" }, last: { kind: "none" },
    description: "", has_freeze: false, has_bell: false, bell_at: null, has_sfx: false,
    video_url: null, stale: false,
    ...partial,
  };
}

describe("Player", () => {
  it("renders the empty state before any scene renders", () => {
    render(<Player scenes={[scene({})]} />);
    expect(screen.getByText(/No renders yet/)).toBeTruthy();
  });

});
