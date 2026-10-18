import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { chatStream } from "../api";
import { Chat } from "./Chat";

vi.mock("../api", () => ({ chatStream: vi.fn() }));

describe("Chat", () => {
  it("empty state is just the input — paperclip and Send, no hint, no starter chips", () => {
    render(<Chat />);
    expect(screen.queryByText(/Ask the agent/)).toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(3); // 🖼 sel + 📎 + Send
    expect(screen.getByLabelText("attach files")).toBeTruthy();
    expect(screen.getByLabelText("send selection image")).toBeTruthy();
    const input = screen.getByLabelText("message the agent") as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("sending shows the user entry and streams the agent reply", async () => {
    async function* stream() {
      yield { type: "message" as const, text: "done — scene 2 is shorter now" };
    }
    vi.mocked(chatStream).mockImplementation(stream);
    render(<Chat />);
    const input = screen.getByLabelText("message the agent");
    fireEvent.change(input, { target: { value: "make scene 2 shorter" } });
    fireEvent.click(screen.getByText("Send"));
    expect(await screen.findByText("make scene 2 shorter")).toBeTruthy();
    expect(await screen.findByText("done — scene 2 is shorter now")).toBeTruthy();
    // conversation started: the starter chips make way for the log
    expect(screen.queryByText(/Ask the agent/)).toBeNull();
  });
});
