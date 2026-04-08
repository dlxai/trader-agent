import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { ChatMessage } from "../../src/components/ChatMessage.js";

describe("ChatMessage", () => {
  it("renders a user message with the provided content", () => {
    render(<ChatMessage role="user" content="hello from user" />);
    expect(screen.getByText("hello from user")).toBeDefined();
  });

  it("renders an assistant message with agent name and icon", () => {
    render(
      <ChatMessage
        role="assistant"
        content="assistant reply"
        agentIcon="\u{1F9E0}"
        agentName="Analyzer"
      />,
    );
    expect(screen.getByText("assistant reply")).toBeDefined();
    expect(screen.getByText("Analyzer")).toBeDefined();
  });

  it("renders a system message with coordinator-style heading", () => {
    render(
      <ChatMessage
        role="system"
        content="Coordinator brief body"
        agentIcon="\u{1F6E1}\uFE0F"
        agentName="Risk Manager"
      />,
    );
    expect(screen.getByText("Coordinator brief body")).toBeDefined();
    expect(screen.getByText(/Risk Manager/)).toBeDefined();
    expect(screen.getByText(/system/i)).toBeDefined();
  });
});
