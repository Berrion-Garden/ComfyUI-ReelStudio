import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AssetImg } from "./AssetImg";

describe("AssetImg", () => {
  it("a load error swaps the image for the bad slot with the slug", () => {
    render(<AssetImg src="/f/a.png" alt="dunk01" />);
    expect(screen.getByAltText("dunk01")).toBeTruthy();
    fireEvent.error(screen.getByAltText("dunk01"));
    const bad = screen.getByTestId("bad-img-dunk01");
    expect(bad.textContent).toContain("✕");
    expect(bad.textContent).toContain("dunk01");
  });

  it("a changed src retries — a regenerated file renders again", () => {
    const { rerender } = render(<AssetImg src="/f/a.png" alt="dunk01" />);
    fireEvent.error(screen.getByAltText("dunk01"));
    expect(screen.getByTestId("bad-img-dunk01")).toBeTruthy();
    rerender(<AssetImg src="/f/a.png?v=2" alt="dunk01" />);
    expect(screen.queryByTestId("bad-img-dunk01")).toBeNull();
    expect(screen.getByAltText("dunk01")).toBeTruthy();
  });

  it("a good image never shows the bad slot", () => {
    render(<AssetImg src="/f/a.png" alt="ok_thing" />);
    expect(screen.queryByTestId("bad-img-ok_thing")).toBeNull();
  });
});
