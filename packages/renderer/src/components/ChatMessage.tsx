import React from "react";
import { theme } from "../theme.js";

export type ChatMessageRole = "user" | "assistant" | "system";
export type AgentId = "analyzer" | "reviewer" | "risk_manager";

export interface ChatMessageProps {
  role: ChatMessageRole;
  content: string;
  agentIcon?: string;
  agentName?: string;
  isStreaming?: boolean;
}

export function ChatMessage({ role, content, agentIcon, agentName, isStreaming }: ChatMessageProps) {
  if (role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <div
          style={{
            maxWidth: "70%",
            background: theme.colors.purple,
            color: theme.colors.white,
            padding: "12px 16px",
            borderRadius: "16px 16px 4px 16px",
            fontSize: 14,
            lineHeight: 1.4,
            whiteSpace: "pre-wrap",
          }}
        >
          {content}
        </div>
      </div>
    );
  }

  if (role === "system") {
    return (
      <div
        style={{
          background: theme.colors.purpleBg,
          borderLeft: `3px solid ${theme.colors.purple}`,
          padding: "12px 16px",
          borderRadius: 8,
          marginBottom: 20,
          fontSize: 13,
          color: theme.colors.nearBlack,
          whiteSpace: "pre-wrap",
          lineHeight: 1.5,
        }}
      >
        {agentName !== undefined && (
          <div
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              color: theme.colors.purpleDark,
              fontWeight: theme.font.weights.bold,
              marginBottom: 4,
              letterSpacing: 0.4,
            }}
          >
            {agentIcon ?? "\u{1F6E1}\uFE0F"} {agentName} — system
          </div>
        )}
        {content}
      </div>
    );
  }

  // assistant
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: theme.colors.purpleSubtle,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 16,
          flexShrink: 0,
        }}
      >
        {agentIcon ?? "\u{1F916}"}
      </div>
      <div style={{ maxWidth: "80%" }}>
        {agentName !== undefined && (
          <div
            style={{
              fontSize: 11,
              color: theme.colors.silverBlue,
              fontWeight: theme.font.weights.medium,
              marginBottom: 4,
            }}
          >
            {agentName}
          </div>
        )}
        <div
          style={{
            background: theme.colors.white,
            border: `1px solid ${theme.colors.borderGray}`,
            padding: "14px 18px",
            borderRadius: "4px 16px 16px 16px",
            fontSize: 14,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          {content}
          {isStreaming && (
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                background: theme.colors.purple,
                borderRadius: "50%",
                marginLeft: 4,
                animation: "pulse 1s ease-in-out infinite",
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
