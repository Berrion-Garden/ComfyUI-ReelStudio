import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { chatStream } from "../api";
import { Chat } from "./Chat";

vi.mock("../api", () => ({ chatStream: vi.fn() }));

describe("Chat", () => {
  it("empty state offers starter prompts that fill the input", () => {
    render(<Chat />);
    const starters = screen.getAllByRole("button", { name: /scene|junction|stale/ });
    expect(starters.length).toBe(3);
    fireEvent.click(starters[0]);
    const input = screen.getByLabelText("message the agent") as HTMLInputElement;
    expect(input.value).toBe(starters[0].textContent);
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
