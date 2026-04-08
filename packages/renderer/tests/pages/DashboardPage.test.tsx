import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage } from "../../src/pages/DashboardPage.js";

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
}

describe("DashboardPage", () => {
  it("renders the page title and Run Reviewer button", () => {
    renderDashboard();
    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByRole("button", { name: /run reviewer now/i })).toBeDefined();
  });

  it("renders all four KPI cards with mock portfolio values", () => {
    renderDashboard();
    // Equity
    expect(screen.getByText("Equity")).toBeDefined();
    expect(screen.getByText("$10127.50")).toBeDefined();
    expect(screen.getByText("+$127.50 today")).toBeDefined();
    // Open positions
    expect(screen.getByText("Open positions")).toBeDefined();
    expect(screen.getByText("3 / 8")).toBeDefined();
    expect(screen.getByText("Exposure $342")).toBeDefined();
    // 7d Win rate
    expect(screen.getByText("7d Win rate")).toBeDefined();
    expect(screen.getByText("62.5%")).toBeDefined();
    expect(screen.getByText("15 / 24 trades")).toBeDefined();
    // Drawdown
    expect(screen.getByText("Drawdown")).toBeDefined();
    expect(screen.getByText("-1.2%")).toBeDefined();
    expect(screen.getByText("From peak $10250")).toBeDefined();
  });

  it("renders the coordinator banner summary", () => {
    renderDashboard();
    expect(screen.getByText(/Coordinator Brief \u2014 23m ago/)).toBeDefined();
    expect(
      screen.getByText(/7 triggers detected in last hour, 2 entered/),
    ).toBeDefined();
  });

  it("renders the position table with all mock positions", () => {
    renderDashboard();
    expect(screen.getByText("Open Positions")).toBeDefined();
    expect(screen.getByText("Trump approval > 50% by May")).toBeDefined();
    expect(screen.getByText("BTC > $100k by Apr 10")).toBeDefined();
    expect(screen.getByText("Lakers vs Celtics tonight")).toBeDefined();
    // PnL signs
    expect(screen.getByText(/\+\$8\.02/)).toBeDefined();
    expect(screen.getByText(/-\$2\.49/)).toBeDefined();
    expect(screen.getByText(/\+\$3\.81/)).toBeDefined();
  });
});
