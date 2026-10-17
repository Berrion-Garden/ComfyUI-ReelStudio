import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Timeline } from "./Timeline";
import type { SceneView } from "../types";

function scene(partial: Partial<SceneView>): SceneView {
  return {
    id: "s1",
    next: null,
    index: 0,
    mode: "i2v",
    frames: 107,
    duration_s: 4.4583,
    first: { kind: "none" },
    last: { kind: "none" },
    description: "",
    has_freeze: false,
    has_bell: false,
    video_url: null,
    stale: false,
    start_s: 0,
    ...partial,
  };
}

const noop = () => "";

describe("Timeline", () => {
  it("renders one vertical slice per scene with XXX for missing video", () => {
    render(
      <Timeline
        scenes={[scene({ id: "s1_ramen" }), scene({ id: "s2", start_s: 4.5 })]}
        music={[]}
        totalS={9}
        artifactUrl={noop}
        playheadPct={null}
      />,
    );
    expect(screen.getByTestId("slice-s1_ramen")).toBeTruthy();
    expect(screen.getByTestId("slice-s2")).toBeTruthy();
    expect(screen.getAllByText("XXX").length).toBe(2);
  });

  it("shows a video element for rendered scenes", () => {
    render(
      <Timeline
        scenes={[scene({ id: "s1", video_url: "/reelstudio/api/scene/s1/artifact/video", stale: false })]}
        music={[]}
        totalS={4.5}
        artifactUrl={noop}
        playheadPct={null}
      />,
    );
    expect(screen.getByTestId("slice-s1").querySelector("video")).toBeTruthy();
    expect(screen.queryByText("XXX")).toBeNull();
  });

  it("stale scenes get a per-scene render button", () => {
    const onRender = vi.fn();
    render(
      <Timeline
        scenes={[scene({ id: "s2", stale: true })]}
        music={[]}
        totalS={4.5}
        artifactUrl={noop}
        onRenderScene={onRender}
        playheadPct={null}
      />,
    );
    const button = screen.getByText("↻ render");
    button.click();
    expect(onRender).toHaveBeenCalledWith("s2");
  });

  it("prev_last anchor is labelled, not an image", () => {
    render(
      <Timeline
        scenes={[scene({ id: "s2", first: { kind: "prev_last" } })]}
        music={[]}
        totalS={4.5}
        artifactUrl={noop}
        playheadPct={null}
      />,
    );
    expect(screen.getByText("⟵ prev")).toBeTruthy();
  });
});
