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

  it("renders one spanning lane per music segment", () => {
    render(
      <Timeline
        scenes={[
          scene({ id: "s1", start_s: 0, duration_s: 4.5 }),
          scene({ id: "s2", start_s: 4.5, duration_s: 4.5 }),
        ]}
        music={[{ name: "opening", start_s: 0, duration_s: 4.5, gain: 1, stale: false, present: true, url: "/m.wav" }]}
        totalS={9}
        artifactUrl={noop}
        playheadPct={null}
      />,
    );
    const lane = screen.getByTestId("lane-opening");
    const block = lane.querySelector(".music-block") as HTMLElement;
    expect(block).toBeTruthy();
    // spans exactly the first scene's column
    expect(block.style.gridColumn).toBe("1 / 2");
    expect(lane.querySelectorAll("audio").length).toBe(1);
  });

  it("unrendered music shows its XXX placeholder, not a player", () => {
    render(
      <Timeline
        scenes={[scene({ id: "s1", start_s: 0, duration_s: 4.5 })]}
        music={[{ name: "battle", start_s: 0, duration_s: 4.5, gain: 1, stale: false, present: false, url: null }]}
        totalS={4.5}
        artifactUrl={noop}
        playheadPct={null}
      />,
    );
    expect(screen.getByText(/XXX battle/)).toBeTruthy();
    expect(screen.getByTestId("lane-battle").querySelector("audio")).toBeNull();
  });

  it("pointer scrub reports the clicked position as a percentage", () => {
    const onSeek = vi.fn();
    const { container } = render(
      <Timeline
        scenes={[scene({ id: "s1", start_s: 0, duration_s: 10 })]}
        music={[]}
        totalS={10}
        artifactUrl={noop}
        playheadPct={null}
        onSeek={onSeek}
      />,
    );
    const track = container.querySelector(".timeline-track") as HTMLElement;
    track.getBoundingClientRect = () =>
      ({ left: 0, width: 200, top: 0, height: 100, right: 200, bottom: 100, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
    const ev = new MouseEvent("pointerdown", { clientX: 50, bubbles: true }) as PointerEvent;
    (ev as unknown as { pointerId: number }).pointerId = 1;
    track.dispatchEvent(ev);
    expect(onSeek).toHaveBeenCalledWith(25);
  });
});
