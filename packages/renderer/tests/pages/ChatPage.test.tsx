import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { ChatPage } from "../../src/pages/ChatPage.js";

function renderChat() {
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  it("renders the Chat title and subtitle", () => {
    renderChat();
    expect(screen.getByText(/Chat .* Hall/)).toBeDefined();
    expect(screen.getByText(/All agents \(Hall\)/)).toBeDefined();
  });

  it("renders the Sidebar with pending proposal badge", () => {
    renderChat();
    const nav = screen.getByRole("navigation");
    expect(within(nav).getByText(/Chat/)).toBeDefined();
    expect(within(nav).getByText("2")).toBeDefined();
  });

  it("renders the coordinator brief as a system message by default", () => {
    renderChat();
    expect(
      screen.getByText(/Coordinator brief .* auto-generated 23 min ago/),
    ).toBeDefined();
    expect(
      screen.getByText(/7 triggers detected in past hour, 2 entered/),
    ).toBeDefined();
  });

  it("renders mock Hall messages from all three agents when filter is All", () => {
    renderChat();
    const region = screen.getByTestId("hall-messages");
    expect(within(region).getByText(/Scanning 142 active markets/)).toBeDefined();
    expect(within(region).getByText(/Weekly review snapshot/)).toBeDefined();
    expect(within(region).getByText(/Currently safe on all halts/)).toBeDefined();
    expect(
      within(region).getByText(
        /@analyzer what's driving the BTC market's acceleration right now\?/,
      ),
    ).toBeDefined();
  });

  it("renders all three agent tabs plus an All tab", () => {
    renderChat();
    expect(screen.getByRole("button", { name: "All agents" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Analyzer" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Reviewer" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Risk Manager" })).toBeDefined();
  });

  it("filters messages to a single agent when an agent tab is clicked", () => {
    renderChat();
    fireEvent.click(screen.getByRole("button", { name: "Analyzer" }));
    const region = screen.getByTestId("hall-messages");
    // Analyzer-only content remains
    expect(within(region).getByText(/Scanning 142 active markets/)).toBeDefined();
    // Reviewer content is gone
    expect(within(region).queryByText(/Weekly review snapshot/)).toBeNull();
    // Risk manager halts content is gone
    expect(within(region).queryByText(/Currently safe on all halts/)).toBeNull();
  });

  it("returns to the full Hall view when the All tab is clicked", () => {
    renderChat();
    fireEvent.click(screen.getByRole("button", { name: "Reviewer" }));
    const region = screen.getByTestId("hall-messages");
    expect(within(region).queryByText(/Scanning 142 active markets/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "All agents" }));
    expect(within(region).getByText(/Scanning 142 active markets/)).toBeDefined();
    expect(within(region).getByText(/Weekly review snapshot/)).toBeDefined();
  });
});
