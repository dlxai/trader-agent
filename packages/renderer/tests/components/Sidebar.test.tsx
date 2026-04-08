import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../../src/components/Sidebar.js";

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar pendingProposalCount={2} />
    </MemoryRouter>
  );
}

describe("Sidebar", () => {
  it("renders all 4 page links", () => {
    renderSidebar();
    expect(screen.getByText(/Dashboard/)).toBeDefined();
    expect(screen.getByText(/Settings/)).toBeDefined();
    expect(screen.getByText(/Reports/)).toBeDefined();
    expect(screen.getByText(/Chat/)).toBeDefined();
  });

  it("shows pending proposal count badge on Settings", () => {
    renderSidebar();
    expect(screen.getByText("2")).toBeDefined();
  });

  it("renders all 3 employee names", () => {
    renderSidebar();
    expect(screen.getByText(/Analyzer/)).toBeDefined();
    expect(screen.getByText(/Reviewer/)).toBeDefined();
    expect(screen.getByText(/Risk Mgr/)).toBeDefined();
  });
});
