import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { SettingsPage } from "../../src/pages/SettingsPage.js";

function renderSettings() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

describe("SettingsPage", () => {
  it("renders the page title and subtitle", () => {
    renderSettings();
    expect(screen.getByText("Settings")).toBeDefined();
    expect(
      screen.getByText(
        /Configure providers, thresholds, and review pending changes/,
      ),
    ).toBeDefined();
  });

  it("renders all four section headers", () => {
    renderSettings();
    expect(screen.getByText(/LLM Providers/)).toBeDefined();
    expect(screen.getByText(/Trading Thresholds/)).toBeDefined();
    expect(screen.getByText(/Risk Limits/)).toBeDefined();
    expect(screen.getByText(/Pending Filter Proposals/)).toBeDefined();
  });

  it("renders API-key providers and marks Anthropic as connected", () => {
    renderSettings();
    expect(screen.getByText("Anthropic")).toBeDefined();
    expect(screen.getByText("DeepSeek")).toBeDefined();
    expect(screen.getByText("Zhipu / Z.ai")).toBeDefined();
    expect(screen.getByText("OpenAI")).toBeDefined();
    expect(screen.getByText(/sk-ant-\.\.\.4f2a/)).toBeDefined();
    expect(
      screen.getByText(/Models: claude-opus-4-6, claude-sonnet-4-6/),
    ).toBeDefined();
  });

  it("renders subscription and OAuth providers", () => {
    renderSettings();
    expect(screen.getByText("Claude (Sub)")).toBeDefined();
    expect(screen.getByText("Gemini (OAuth)")).toBeDefined();
    expect(screen.getByText(/Max plan/)).toBeDefined();
    expect(screen.getByText(/Free tier/)).toBeDefined();
  });

  it("renders per-agent model assignments", () => {
    renderSettings();
    expect(screen.getByText("claude-opus-4-6")).toBeDefined();
    expect(screen.getByText("claude-sonnet-4-6")).toBeDefined();
    expect(screen.getByText("gemini-2.5-flash")).toBeDefined();
    expect(screen.getAllByText("via anthropic_subscription").length).toBe(2);
    expect(screen.getByText("via gemini_oauth")).toBeDefined();
  });

  it("renders trading threshold rows with mock values", () => {
    renderSettings();
    expect(screen.getByText("Min trade size")).toBeDefined();
    expect(screen.getByText("$200")).toBeDefined();
    expect(screen.getByText("Min net flow (1m)")).toBeDefined();
    expect(screen.getByText("$3500")).toBeDefined();
    expect(screen.getByText("auto-applied")).toBeDefined();
    expect(screen.getByText("Dead zone")).toBeDefined();
    expect(screen.getByText("[0.6, 0.85]")).toBeDefined();
    expect(screen.getByText("locked")).toBeDefined();
  });

  it("renders risk limits with formatted values", () => {
    renderSettings();
    expect(screen.getByText("Total capital")).toBeDefined();
    expect(screen.getByText("$10,000")).toBeDefined();
    expect(screen.getByText("Max position size")).toBeDefined();
    expect(screen.getByText("$300")).toBeDefined();
    expect(screen.getByText("Max open positions")).toBeDefined();
    expect(screen.getByText("8")).toBeDefined();
    expect(screen.getByText("+10% / -7%")).toBeDefined();
  });

  it("renders both mock pending proposals", () => {
    renderSettings();
    expect(screen.getByText(/Pending Filter Proposals \(2\)/)).toBeDefined();
    expect(screen.getByText(/min_unique_traders_1m/)).toBeDefined();
    expect(screen.getByText(/take_profit_pct/)).toBeDefined();
    expect(
      screen.getByText(/tightening filter projected to lift/),
    ).toBeDefined();
  });

  it("removes a proposal locally when Approve is clicked", () => {
    renderSettings();
    const approveButtons = screen.getAllByRole("button", { name: /approve/i });
    expect(approveButtons.length).toBe(2);
    fireEvent.click(approveButtons[0]!);
    expect(screen.getByText(/Pending Filter Proposals \(1\)/)).toBeDefined();
    expect(screen.queryByText(/min_unique_traders_1m/)).toBeNull();
  });

  it("removes a proposal locally when Reject is clicked", () => {
    renderSettings();
    const rejectButtons = screen.getAllByRole("button", { name: /reject/i });
    fireEvent.click(rejectButtons[1]!);
    expect(screen.getByText(/Pending Filter Proposals \(1\)/)).toBeDefined();
    expect(screen.queryByText(/take_profit_pct/)).toBeNull();
  });

  it("shows empty state once all proposals are cleared", () => {
    renderSettings();
    const approveButtons = screen.getAllByRole("button", { name: /approve/i });
    fireEvent.click(approveButtons[0]!);
    const remaining = screen.getAllByRole("button", { name: /approve/i });
    fireEvent.click(remaining[0]!);
    expect(screen.getByText(/Pending Filter Proposals \(0\)/)).toBeDefined();
    expect(screen.getByText("No pending proposals.")).toBeDefined();
  });

  it("shows the pending proposal badge count in the sidebar", () => {
    renderSettings();
    const nav = screen.getByRole("navigation");
    expect(within(nav).getByText("2")).toBeDefined();
  });
});
