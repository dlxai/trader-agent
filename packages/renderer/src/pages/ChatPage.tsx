import React, { useEffect, useMemo, useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import {
  ChatMessage,
  type AgentId,
} from "../components/ChatMessage.js";
import { EmployeeTab } from "../components/EmployeeTab.js";
import { useChat } from "../stores/chat.js";
import { useSettings } from "../stores/settings.js";

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
  if (match === undefined) {
    throw new Error(`Unknown agent id: ${id}`);
  }
  return match;
}

export function ChatPage() {
  const [filter, setFilter] = useState<AgentFilter>("all");
  const [draft, setDraft] = useState<string>("");
  const messagesByAgent = useChat((s) => s.messagesByAgent);
  const pendingProposalCount = useSettings((s) => s.pendingProposals.length);

  // Hall coordination model: the chat store keeps per-agent arrays internally,
  // but the Hall view flattens + sorts them by timestamp so all three agents
  // share one conversation thread. Agent tabs filter the flattened list.
  const flattened = useMemo(() => {
    const all = [
      ...messagesByAgent.analyzer.map((m) => ({ ...m, agentId: "analyzer" as AgentId })),
      ...messagesByAgent.reviewer.map((m) => ({ ...m, agentId: "reviewer" as AgentId })),
      ...messagesByAgent.risk_manager.map((m) => ({
        ...m,
        agentId: "risk_manager" as AgentId,
      })),
    ];
    all.sort((a, b) => a.timestamp - b.timestamp);
    return all;
  }, [messagesByAgent]);

  const visibleMessages =
    filter === "all" ? flattened : flattened.filter((m) => m.agentId === filter);

  const activeLabel =
    filter === "all" ? "All agents (Hall)" : getAgentMeta(filter).name;

  const activeModel =
    filter === "all"
      ? MOCK_AGENTS.map((a) => a.model).join(" \u00B7 ")
      : getAgentMeta(filter).model;

  useEffect(() => {
    void useChat.getState().loadHistory("analyzer");
    void useChat.getState().loadHistory("reviewer");
    void useChat.getState().loadHistory("risk_manager");
  }, []);

  const handleSend = () => {
    const text = draft.trim();
    if (text.length === 0) return;
    const target: AgentId = filter === "all" ? "risk_manager" : filter;
    void useChat.getState().sendMessage(target, text);
    setDraft("");
  };

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={pendingProposalCount} />
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
                      key={String(m.id)}
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
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSend();
                }}
              />
              <button type="button" style={sendButtonStyle} onClick={handleSend}>
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
