import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { chatStream } from "../api";
import { FloatingChat } from "./FloatingChat";

vi.mock("../api", () => ({ chatStream: vi.fn(), uploadFile: vi.fn() }));

// jsdom defaults the viewport to 1024×768
const VW = 1024;
const VH = 768;
const winEl = () => screen.getByTestId("floating-chat") as HTMLElement;
const bar = () => screen.getByLabelText(/agent chat window/) as HTMLElement;
const tabs = () => screen.getAllByRole("tab") as HTMLElement[];
const saved = (g: { x: number; y: number; w: number; h: number }) =>
  localStorage.setItem("reelstudio.chat.geometry.v1", JSON.stringify(g));

describe("FloatingChat", () => {
  // geometry persists to localStorage — isolate every case
  beforeEach(() => localStorage.clear());
  it("opens as a fixed overlay docked along the bottom, full width", () => {
    render(<FloatingChat />);
    const el = winEl();
    expect(el.style.left).toBe("0px");
    expect(el.style.top).toBe(`${VH - 320}px`);
    expect(el.style.width).toBe(`${VW}px`);
    expect(el.style.height).toBe("320px");
    // empty state: minimize + new session + sel + paperclip + Send,
    // one session tab, no starter hints
    expect(screen.queryAllByRole("button")).toHaveLength(5);
    expect(tabs()).toHaveLength(1);
    expect(screen.getByLabelText("attach files")).toBeTruthy();
    expect(screen.getByLabelText("send selection image")).toBeTruthy();
    expect(screen.getByLabelText("message the agent")).toBeTruthy();
  });

  it("drags by the title bar and parks flush when released near an edge", () => {
    render(<FloatingChat />);
    const el = winEl();
    // a full-width window always parks at the right/bottom edges on release,
    // so shrink it first (to 516×258) before testing free movement
    const handle = screen.getByTestId("floating-chat-resize");
    fireEvent.pointerDown(handle, { clientX: 1018, clientY: 762, button: 0 });
    fireEvent.pointerMove(window, { clientX: 510, clientY: 690 });
    fireEvent.pointerUp(window);
    expect(el.style.width).toBe("516px");
    expect(el.style.height).toBe("248px");
    // grab the title bar at (250, 460) and drag to (400, 500): +150, +40
    fireEvent.pointerDown(bar(), { clientX: 250, clientY: 460, button: 0 });
    fireEvent.pointerMove(window, { clientX: 400, clientY: 500 });
    expect(el.style.left).toBe("150px");
    expect(el.style.top).toBe("488px");
    fireEvent.pointerUp(window); // mid-screen: no snap
    expect(el.style.left).toBe("150px");
    expect(el.style.top).toBe("488px");
    // drag 3px past the left edge and release → parks flush
    fireEvent.pointerDown(bar(), { clientX: 160, clientY: 495, button: 0 });
    fireEvent.pointerMove(window, { clientX: 7, clientY: 495 });
    expect(el.style.left).toBe("-3px");
    fireEvent.pointerUp(window);
    expect(el.style.left).toBe("0px");
  });

  it("clamps the window so the title bar stays reachable while dragging", () => {
    render(<FloatingChat />);
    const el = winEl();
    fireEvent.pointerDown(bar(), { clientX: 512, clientY: 460, button: 0 });
    fireEvent.pointerMove(window, { clientX: -800, clientY: -500 });
    fireEvent.pointerUp(window);
    // only 60px of the title bar may leave the left edge; the bar stays on screen
    expect(parseFloat(el.style.left)).toBeGreaterThan(-VW + 60 - 1);
    expect(el.style.top).toBe("0px");
  });

  it("resizes from the corner, clamps at the minimum, and snaps to the viewport edge", () => {
    render(<FloatingChat />);
    const el = winEl();
    const handle = () => screen.getByTestId("floating-chat-resize");
    // default bottom-right corner is (1024, 768)
    fireEvent.pointerDown(handle(), { clientX: 1018, clientY: 762, button: 0 });
    fireEvent.pointerMove(window, { clientX: 400, clientY: 560 });
    // w = 1024 + (400−1018) = 406; h = 320 + (560−762) = −182 → clamped to 200
    expect(el.style.width).toBe("406px");
    expect(el.style.height).toBe("200px");
    fireEvent.pointerUp(window);
    // drag the corner out toward the bottom-right corner: stretches flush
    fireEvent.pointerDown(handle(), { clientX: 400, clientY: 642, button: 0 });
    fireEvent.pointerMove(window, { clientX: 1100, clientY: 900 });
    fireEvent.pointerUp(window);
    expect(el.style.width).toBe(`${VW}px`);
    expect(el.style.height).toBe(`${VH - 448}px`);
  });

  it("resizes from the top-right corner, keeping the left edge put", () => {
    saved({ x: 200, y: 200, w: 400, h: 300 });
    render(<FloatingChat />);
    const el = winEl();
    fireEvent.pointerDown(screen.getByTestId("floating-chat-resize-ne"),
      { clientX: 594, clientY: 206, button: 0 });
    fireEvent.pointerMove(window, { clientX: 700, clientY: 120 });
    // dx = +106, dy = −86: the right/top edges follow the pointer, the
    // left/bottom stay put: w = 400+106 = 506 (x stays 200);
    // h = 300+86 = 386, top = 500−386 = 114
    expect(el.style.left).toBe("200px");
    expect(el.style.width).toBe("506px");
    expect(el.style.top).toBe("114px");
    expect(el.style.height).toBe("386px");
    fireEvent.pointerUp(window);
  });

  it("resizes from the bottom-left corner, keeping the top edge put", () => {
    saved({ x: 200, y: 200, w: 400, h: 300 });
    render(<FloatingChat />);
    const el = winEl();
    fireEvent.pointerDown(screen.getByTestId("floating-chat-resize-sw"),
      { clientX: 206, clientY: 494, button: 0 });
    fireEvent.pointerMove(window, { clientX: 300, clientY: 620 });
    // dx = +94, dy = +126: w = 400−94 = 306, left = 600−306 = 294;
    // h = 300+126 = 426 (top stays 200)
    expect(el.style.left).toBe("294px");
    expect(el.style.width).toBe("306px");
    expect(el.style.top).toBe("200px");
    expect(el.style.height).toBe("426px");
    fireEvent.pointerUp(window);
  });

  it("resizes from the top-left corner and parks flush at the top-left on release", () => {
    saved({ x: 200, y: 200, w: 400, h: 300 });
    render(<FloatingChat />);
    const el = winEl();
    fireEvent.pointerDown(screen.getByTestId("floating-chat-resize-nw"),
      { clientX: 206, clientY: 206, button: 0 });
    fireEvent.pointerMove(window, { clientX: 8, clientY: 8 });
    // dx = dy = −198: w = 598, left = 600−598 = 2; h = 498, top = 500−498 = 2
    expect(el.style.left).toBe("2px");
    expect(el.style.top).toBe("2px");
    fireEvent.pointerUp(window); // both inside the 12px margin → dock to 0
    expect(el.style.left).toBe("0px");
    expect(el.style.top).toBe("0px");
    // the opposite (right/bottom) edges keep their position: 600 / 500
    expect(el.style.width).toBe("600px");
    expect(el.style.height).toBe("500px");
  });

  it("minimizes to the title bar and restores", () => {
    render(<FloatingChat />);
    const el = winEl();
    // styles.css isn't loaded in jsdom: assert the state the CSS keys off
    fireEvent.click(screen.getByLabelText("minimize chat"));
    expect(el.style.height).toBe("36px");
    expect(el.classList.contains("min")).toBe(true);
    fireEvent.click(screen.getByLabelText("restore chat"));
    expect(el.style.height).toBe("320px");
    expect(el.classList.contains("min")).toBe(false);
  });

  it("adds a session tab via + and can close all but the last", () => {
    render(<FloatingChat />);
    expect(tabs()).toHaveLength(1);
    expect(screen.queryByLabelText("close session 1")).toBeNull();
    fireEvent.click(screen.getByLabelText("new chat session"));
    expect(tabs()).toHaveLength(2);
    expect(tabs()[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByLabelText("close session 2"));
    expect(tabs()).toHaveLength(1);
    expect(tabs()[0].getAttribute("aria-selected")).toBe("true");
    // the last tab has no close button
    expect(screen.queryByLabelText("close session 1")).toBeNull();
  });

  it("tabs hold separate agent contexts", async () => {
    // echo how much history the request carried — cross-talk would show up here
    async function* stream(message: string, history: { role: string; content: string }[]) {
      yield { type: "message" as const, text: `${message} → saw ${history.length} prior` };
    }
    vi.mocked(chatStream).mockImplementation(stream);
    render(<FloatingChat />);
    const input = () => screen.getByLabelText("message the agent");
    fireEvent.change(input(), { target: { value: "hello tab one" } });
    fireEvent.click(screen.getByText("Send"));
    expect(await screen.findByText("hello tab one → saw 0 prior")).toBeTruthy();
    // a second session starts with a blank slate — tab one's log entries
    // are gone (its auto-title still shows in the tab strip, by design)
    fireEvent.click(screen.getByLabelText("new chat session"));
    expect(screen.queryByText("hello tab one → saw 0 prior")).toBeNull();
    fireEvent.change(input(), { target: { value: "hello tab two" } });
    fireEvent.click(screen.getByText("Send"));
    // still 0 prior: tab two's context did not inherit tab one's history
    expect(await screen.findByText("hello tab two → saw 0 prior")).toBeTruthy();
    // switching back brings tab one's conversation back
    fireEvent.click(tabs()[0]);
    expect(screen.getByText("hello tab one → saw 0 prior")).toBeTruthy();
  });

  it("restores the saved geometry and saves after a drag", () => {
    localStorage.setItem("reelstudio.chat.geometry.v1",
      JSON.stringify({ x: 120, y: 80, w: 500, h: 260 }));
    render(<FloatingChat />);
    const el = winEl();
    expect(el.style.left).toBe("120px");
    expect(el.style.top).toBe("80px");
    expect(el.style.width).toBe("500px");
    expect(el.style.height).toBe("260px");
    fireEvent.pointerDown(bar(), { clientX: 125, clientY: 85, button: 0 });
    fireEvent.pointerMove(window, { clientX: 200, clientY: 85 });
    fireEvent.pointerUp(window);
    const savedGeo = (JSON.parse(
      localStorage.getItem("reelstudio.chat.geometry.v1")!) as { x: number; y: number });
    expect(savedGeo.x).toBe(195);
    expect(savedGeo.y).toBe(80);
    localStorage.clear();
  });

  it("rejects a corrupt saved geometry and falls back to the default", () => {
    localStorage.setItem("reelstudio.chat.geometry.v1", "{not json");
    render(<FloatingChat />);
    const el = winEl();
    expect(el.style.left).toBe("0px");
    expect(el.style.width).toBe(`${VW}px`);
    localStorage.clear();
  });

  it("sending shows the user entry and streams the agent reply", async () => {
    async function* stream() {
      yield { type: "message" as const, text: "done — scene 2 is shorter now" };
    }
    vi.mocked(chatStream).mockImplementation(stream);
    render(<FloatingChat />);
    const input = screen.getByLabelText("message the agent");
    fireEvent.change(input, { target: { value: "make scene 2 shorter" } });
    fireEvent.click(screen.getByText("Send"));
    // the first message names the tab, so the text appears twice:
    // the tab pill and the user's entry
    expect((await screen.findAllByText("make scene 2 shorter")).length).toBe(2);
    expect(await screen.findByText("done — scene 2 is shorter now")).toBeTruthy();
    expect(await screen.findByText("Agent")).toBeTruthy();
  });
});
