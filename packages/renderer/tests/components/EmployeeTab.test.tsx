import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { EmployeeTab } from "../../src/components/EmployeeTab.js";

describe("EmployeeTab", () => {
  it("renders the icon and label", () => {
    render(
      <EmployeeTab icon="\u{1F9E0}" label="Analyzer" isActive={false} onClick={() => {}} />,
    );
    const btn = screen.getByRole("button", { name: "Analyzer" });
    expect(btn).toBeDefined();
    expect(btn.getAttribute("aria-pressed")).toBe("false");
  });

  it("reflects the active state via aria-pressed", () => {
    render(
      <EmployeeTab icon="\u{1F4CA}" label="Reviewer" isActive={true} onClick={() => {}} />,
    );
    expect(
      screen.getByRole("button", { name: "Reviewer" }).getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("fires onClick when clicked", () => {
    const spy = vi.fn();
    render(
      <EmployeeTab
        icon="\u{1F6E1}\uFE0F"
        label="Risk Manager"
        isActive={false}
        onClick={spy}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Risk Manager" }));
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
