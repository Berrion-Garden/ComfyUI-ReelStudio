// The validate panel: tick kinds, one reviewer per kind, merged findings.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { fetchValidate, runValidate } from "../api";
import { ValidatePanel } from "./ValidatePanel";

vi.mock("../api", () => ({
  fetchValidate: vi.fn(),
  runValidate: vi.fn(),
}));

const REPORTS = {
  prompts: {
    state: "done", kind: "prompts", total: 3, done: 3,
    findings: [{ item: "s1_ramen", beat: "1.1", verdict: "issue",
                 note: "beat text reworded" }],
  },
  entities: { state: "error", error: "no entity blocks yet" },
  frames: { state: "idle" },
};

describe("ValidatePanel", () => {
  beforeEach(() => {
    vi.mocked(fetchValidate).mockResolvedValue({ reports: REPORTS });
    vi.mocked(runValidate).mockResolvedValue();
  });

  it("ticks kinds, runs each reviewer, and merges their findings", async () => {
    render(<ValidatePanel />);
    expect(await screen.findByText("beat text reworded")).toBeTruthy();
    expect(screen.getByText("⚠ no entity blocks yet")).toBeTruthy();
    // the idle kind shows no section
    expect(screen.queryByText("Rendered frames vs narrative — results"))
      .toBeFalsy();

    fireEvent.click(screen.getByRole("button", { name: "Run 2 reviews" }));
    await waitFor(() => expect(runValidate).toHaveBeenCalledWith(
      ["prompts", "entities"]));
  });

  it("unticking a kind drops it from the run", async () => {
    render(<ValidatePanel />);
    fireEvent.click(await screen.findByLabelText("Characters & locations vs narrative"));
    fireEvent.click(screen.getByRole("button", { name: "Run 1 review" }));
    await waitFor(() => expect(runValidate).toHaveBeenCalledWith(["prompts"]));
  });
});
