import React, { useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import {
  ChatMessage,
  type ChatMessageRole,
  type AgentId,
} from "../components/ChatMessage.js";
import { EmployeeTab } from "../components/EmployeeTab.js";

// M4.15-M4.18 — mock data only. M5 wires real IPC / LLM streams.

interface HallMessage {
  id: string;
  agentId: AgentId;
  role: ChatMessageRole;
  content: string;
  timestamp: number;
}

interface AgentMeta {
  id: AgentId;
  icon: string;
  name: string;
  model: string;
}

const MOCK_AGENTS: readonly AgentMeta[] = [
  { id: "analyzer", icon: "\u{1F9E0}", name: "Analyzer", model: "claude-opus-4-6" },
  { id: "reviewer", icon: "\u{1F4CA}", name: "Reviewer", model: "claude-sonnet-4-6" },
  { id: "risk_manager", icon: "\u{1F6E1}\uFE0F", name: "Risk Manager", model: "gemini-2.5-flash" },
] as const;

const NOW = Date.now();

const MOCK_HALL_MESSAGES: readonly HallMessage[] = [
  {
    id: "m1",
    agentId: "risk_manager",
    role: "system",
    content:
      "Coordinator brief \u00B7 auto-generated 23 min ago\n\n7 triggers detected in past hour, 2 entered (BTC YES, Lakers NO). Net flow on US Election markets unusually elevated \u2014 consider tightening unique_traders_1m to 4.",
    timestamp: NOW - 23 * 60_000,
  },
  {
    id: "m2",
    agentId: "analyzer",
    role: "assistant",
    content:
      "Scanning 142 active markets. Top momentum signals:\n\n- BTC > $100k by Apr 10 (net flow +$4.2k/min)\n- Lakers vs Celtics tonight (unique traders 7/min)\n- Trump approval > 50% by May (steady drift)",
    timestamp: NOW - 18 * 60_000,
  },
  {
    id: "m3",
    agentId: "analyzer",
    role: "user",
    content: "@analyzer what's driving the BTC market's acceleration right now?",
    timestamp: NOW - 15 * 60_000,
  },
  {
    id: "m4",
    agentId: "analyzer",
    role: "assistant",
    content:
      "Three concurrent factors:\n1. Spot BTC cleared $98.2k resistance 11 min ago\n2. Unique traders jumped from 3/min to 9/min\n3. YES side order book thickened 2.4x",
    timestamp: NOW - 14 * 60_000,
  },
  {
    id: "m5",
    agentId: "reviewer",
    role: "assistant",
    content:
      "Weekly review snapshot: bucket 0.40-0.45 remains the standout (71.4% win rate, +$56.20). Recommending we keep current sizing on that bucket and pull back on 0.55-0.60.",
    timestamp: NOW - 11 * 60_000,
  },
  {
    id: "m6",
    agentId: "risk_manager",
    role: "user",
    content: "@risk_manager are we close to any halts? What's our drawdown right now?",
    timestamp: NOW - 5 * 60_000,
  },
  {
    id: "m7",
    agentId: "risk_manager",
    role: "assistant",
    content:
      "Currently safe on all halts:\n\n- Daily DD: -0.8% (halt at -2.0%)\n- Weekly DD: -1.5% (halt at -4.0%)\n- Total DD from peak: -1.2%\n\nRisk budget: $94.50 remaining today.",
    timestamp: NOW - 4 * 60_000,
  },
  {
    id: "m8",
    agentId: "reviewer",
    role: "user",
    content: "@reviewer should we push the filter proposal for min_unique_traders_1m tonight?",
    timestamp: NOW - 2 * 60_000,
  },
] as const;

const MOCK_PENDING_PROPOSAL_COUNT = 2;

type AgentFilter = "all" | AgentId;

const layoutStyle: React.CSSProperties = {
  display: "flex",
  minHeight: "100vh",
  background: theme.colors.fafafa,
};

const contentStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  maxHeight: "100vh",
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  padding: "24px 32px 16px 32px",
  borderBottom: `1px solid ${theme.colors.borderGray}`,
  background: theme.colors.white,
};

const titleStyle: React.CSSProperties = {
  fontSize: 28,
  fontWeight: theme.font.weights.bold,
  letterSpacing: -1,
};

const subtitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: theme.colors.silverBlue,
  marginTop: 4,
};

const bodyStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  overflow: "hidden",
};

const tabsColumnStyle: React.CSSProperties = {
  width: 72,
  borderRight: `1px solid ${theme.colors.borderGray}`,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  padding: "24px 0",
  gap: 16,
  background: theme.colors.white,
};

const conversationStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const messagesScrollStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  padding: "24px 32px",
  background: "#fdfdfd",
};

const inputBarStyle: React.CSSProperties = {
  borderTop: `1px solid ${theme.colors.borderGray}`,
  padding: "16px 32px",
  background: theme.colors.white,
  display: "flex",
  gap: 8,
  alignItems: "center",
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  border: `1px solid ${theme.colors.borderGray}`,
  padding: "12px 16px",
  borderRadius: 12,
  fontSize: 14,
  outline: "none",
};

const sendButtonStyle: React.CSSProperties = {
  background: theme.colors.purple,
  color: theme.colors.white,
  padding: "12px 20px",
  borderRadius: 12,
  fontWeight: theme.font.weights.medium,
  fontSize: 14,
  border: "none",
  cursor: "pointer",
};

const allTabStyle = (isActive: boolean): React.CSSProperties => ({
  width: 44,
  height: 44,
  borderRadius: 12,
  background: isActive ? theme.colors.purple : "rgba(148,151,169,0.08)",
  color: isActive ? theme.colors.white : theme.colors.coolGray,
  fontSize: 11,
  fontWeight: theme.font.weights.semibold,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
  border: "none",
  padding: 0,
});

function getAgentMeta(id: AgentId): AgentMeta {
  const match = MOCK_AGENTS.find((a) => a.id === id);
  // MOCK_AGENTS is a static const that contains every AgentId, so match is defined.
  if (match === undefined) {
    throw new Error(`Unknown agent id: ${id}`);
  }
  return match;
}

export function ChatPage() {
  const [filter, setFilter] = useState<AgentFilter>("all");

  const visibleMessages =
    filter === "all"
      ? MOCK_HALL_MESSAGES
      : MOCK_HALL_MESSAGES.filter((m) => m.agentId === filter);

  const activeLabel =
    filter === "all" ? "All agents (Hall)" : getAgentMeta(filter).name;

  const activeModel =
    filter === "all"
      ? MOCK_AGENTS.map((a) => a.model).join(" \u00B7 ")
      : getAgentMeta(filter).model;

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={MOCK_PENDING_PROPOSAL_COUNT} />
      <div style={contentStyle}>
        <div style={headerStyle}>
          <div style={titleStyle}>Chat {"\u2014"} Hall</div>
          <div style={subtitleStyle}>
            {activeLabel} {"\u00B7 "}
            <span style={{ color: theme.colors.green }}>Online</span>
            {" \u00B7 "}
            {activeModel}
          </div>
        </div>

        <div style={bodyStyle}>
          <div style={tabsColumnStyle} aria-label="Agent filter tabs">
            <button
              type="button"
              aria-pressed={filter === "all"}
              aria-label="All agents"
              onClick={() => setFilter("all")}
              style={allTabStyle(filter === "all")}
            >
              All
            </button>
            {MOCK_AGENTS.map((agent) => (
              <EmployeeTab
                key={agent.id}
                icon={agent.icon}
                label={agent.name}
                isActive={filter === agent.id}
                onClick={() => setFilter(agent.id)}
              />
            ))}
          </div>

          <div style={conversationStyle}>
            <div style={messagesScrollStyle} data-testid="hall-messages">
              {visibleMessages.length === 0 ? (
                <div
                  style={{
                    color: theme.colors.silverBlue,
                    fontSize: 13,
                    textAlign: "center",
                    marginTop: 32,
                  }}
                >
                  No messages for this agent yet.
                </div>
              ) : (
                visibleMessages.map((m) => {
                  const meta = getAgentMeta(m.agentId);
                  return (
                    <ChatMessage
                      key={m.id}
                      role={m.role}
                      content={m.content}
                      agentIcon={meta.icon}
                      agentName={meta.name}
                    />
                  );
                })
              )}
            </div>

            <div style={inputBarStyle}>
              <input
                type="text"
                placeholder={
                  filter === "all"
                    ? "Message the Hall \u2014 use @analyzer, @reviewer, or @risk_manager"
                    : `Message ${getAgentMeta(filter).name}...`
                }
                style={inputStyle}
                disabled
              />
              <button type="button" style={sendButtonStyle} disabled>
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
