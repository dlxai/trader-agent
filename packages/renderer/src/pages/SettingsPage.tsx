import React, { useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { ProviderCard } from "../components/ProviderCard.js";
import { ProposalCard } from "../components/ProposalCard.js";

// M4.7-M4.11 — mock data only. M5 wires real IPC / stores.

interface ProviderInfo {
  id: string;
  name: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  authDetail?: string;
  models?: string[];
}

interface AgentAssignment {
  providerId: string;
  modelId: string;
}

interface PendingProposal {
  id: number;
  field: string;
  oldValue: string;
  proposedValue: string;
  rationale: string;
  sampleCount: number;
  expectedDeltaWinrate: number;
}

const MOCK_PROVIDERS: ProviderInfo[] = [
  {
    id: "anthropic_api",
    name: "Anthropic",
    authType: "api_key",
    isConnected: true,
    authDetail: "sk-ant-...4f2a",
    models: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
  },
  { id: "deepseek", name: "DeepSeek", authType: "api_key", isConnected: false },
  { id: "zhipu", name: "Zhipu / Z.ai", authType: "api_key", isConnected: false },
  { id: "openai", name: "OpenAI", authType: "api_key", isConnected: false },
  {
    id: "anthropic_subscription",
    name: "Claude (Sub)",
    authType: "cli_credential",
    isConnected: true,
    authDetail: "Auto \u00B7 Max plan \u00B7 4d left",
  },
  {
    id: "gemini_oauth",
    name: "Gemini (OAuth)",
    authType: "oauth",
    isConnected: true,
    authDetail: "Free tier \u00B7 1000/day",
  },
];

const MOCK_AGENT_MODELS: Record<
  "analyzer" | "reviewer" | "risk_manager",
  AgentAssignment
> = {
  analyzer: {
    providerId: "anthropic_subscription",
    modelId: "claude-opus-4-6",
  },
  reviewer: {
    providerId: "anthropic_subscription",
    modelId: "claude-sonnet-4-6",
  },
  risk_manager: {
    providerId: "gemini_oauth",
    modelId: "gemini-2.5-flash",
  },
};

const MOCK_THRESHOLDS = {
  minTradeUsdc: 200,
  minNetFlow1m: 3500,
  minUniqueTraders1m: 3,
  minPriceMove5m: 0.03,
  minLiquidity: 5000,
  deadZoneMin: 0.6,
  deadZoneMax: 0.85,
} as const;

const MOCK_RISK_LIMITS = {
  totalCapital: 10000,
  maxPositionUsdc: 300,
  maxSingleLoss: 50,
  maxOpenPositions: 8,
  dailyHaltPct: 0.02,
  takeProfitPct: 0.1,
  stopLossPct: 0.07,
} as const;

const MOCK_PROPOSALS: PendingProposal[] = [
  {
    id: 1,
    field: "min_unique_traders_1m",
    oldValue: "3",
    proposedValue: "4",
    rationale:
      "Bucket 0.40-0.60 win rate is 58% over 22 trades; tightening filter projected to lift to ~64%.",
    sampleCount: 22,
    expectedDeltaWinrate: 0.06,
  },
  {
    id: 2,
    field: "take_profit_pct",
    oldValue: "0.10",
    proposedValue: "0.08",
    rationale: "Past 30 trades show 70% of TP exits happen below +9%.",
    sampleCount: 30,
    expectedDeltaWinrate: 0.04,
  },
];

const layoutStyle: React.CSSProperties = {
  display: "flex",
  minHeight: "100vh",
  background: theme.colors.fafafa,
};

const contentStyle: React.CSSProperties = {
  flex: 1,
  padding: 32,
  maxHeight: "100vh",
  overflowY: "auto",
};

const sectionCardStyle: React.CSSProperties = {
  background: theme.colors.white,
  border: `1px solid ${theme.colors.borderGray}`,
  borderRadius: 12,
  padding: 24,
  marginBottom: 16,
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 18,
  fontWeight: theme.font.weights.semibold,
  marginBottom: 4,
};

const sectionSubtitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: theme.colors.silverBlue,
  marginBottom: 20,
};

const subgroupLabelStyle: React.CSSProperties = {
  fontSize: 11,
  textTransform: "uppercase",
  color: theme.colors.silverBlue,
  fontWeight: theme.font.weights.bold,
  marginBottom: 10,
};

const AGENT_LABELS: Record<"analyzer" | "reviewer" | "risk_manager", string> = {
  analyzer: "\u{1F9E0} Analyzer",
  reviewer: "\u{1F4CA} Reviewer",
  risk_manager: "\u{1F6E1}\uFE0F Risk Mgr",
};

export function SettingsPage() {
  const [proposals, setProposals] = useState<PendingProposal[]>(MOCK_PROPOSALS);

  const handleApprove = (id: number) => {
    setProposals((prev) => prev.filter((p) => p.id !== id));
  };
  const handleReject = (id: number) => {
    setProposals((prev) => prev.filter((p) => p.id !== id));
  };

  const apiKeyProviders = MOCK_PROVIDERS.filter((p) => p.authType === "api_key");
  const subscriptionProviders = MOCK_PROVIDERS.filter(
    (p) => p.authType === "oauth" || p.authType === "cli_credential",
  );

  const thresholdRows: Array<{
    label: string;
    value: string;
    locked: boolean;
    autoApplied?: boolean;
  }> = [
    {
      label: "Min trade size",
      value: `$${MOCK_THRESHOLDS.minTradeUsdc}`,
      locked: false,
    },
    {
      label: "Min net flow (1m)",
      value: `$${MOCK_THRESHOLDS.minNetFlow1m}`,
      locked: false,
      autoApplied: true,
    },
    {
      label: "Min unique traders (1m)",
      value: `${MOCK_THRESHOLDS.minUniqueTraders1m}`,
      locked: false,
    },
    {
      label: "Min price move (5m)",
      value: `${(MOCK_THRESHOLDS.minPriceMove5m * 100).toFixed(1)}%`,
      locked: false,
    },
    {
      label: "Min liquidity",
      value: `$${MOCK_THRESHOLDS.minLiquidity}`,
      locked: false,
    },
    {
      label: "Dead zone",
      value: `[${MOCK_THRESHOLDS.deadZoneMin}, ${MOCK_THRESHOLDS.deadZoneMax}]`,
      locked: true,
    },
  ];

  const riskRows: Array<[string, string]> = [
    ["Total capital", `$${MOCK_RISK_LIMITS.totalCapital.toLocaleString()}`],
    ["Max position size", `$${MOCK_RISK_LIMITS.maxPositionUsdc}`],
    ["Max single-trade loss", `$${MOCK_RISK_LIMITS.maxSingleLoss}`],
    ["Max open positions", `${MOCK_RISK_LIMITS.maxOpenPositions}`],
    [
      "Daily halt threshold",
      `${(MOCK_RISK_LIMITS.dailyHaltPct * 100).toFixed(1)}%`,
    ],
    [
      "Take profit / Stop loss",
      `+${(MOCK_RISK_LIMITS.takeProfitPct * 100).toFixed(0)}% / -${(MOCK_RISK_LIMITS.stopLossPct * 100).toFixed(0)}%`,
    ],
  ];

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={proposals.length} />
      <div style={contentStyle}>
        <div
          style={{
            fontSize: 32,
            fontWeight: theme.font.weights.bold,
            letterSpacing: -1,
            marginBottom: 8,
          }}
        >
          Settings
        </div>
        <div
          style={{
            fontSize: 14,
            color: theme.colors.silverBlue,
            marginBottom: 32,
          }}
        >
          Configure providers, thresholds, and review pending changes
        </div>

        {/* LLM Providers section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>{"\u{1F916}"} LLM Providers</div>
          <div style={sectionSubtitleStyle}>
            Configure API keys and per-agent model overrides
          </div>

          <div style={subgroupLabelStyle}>API Key</div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 12,
              marginBottom: 24,
            }}
          >
            {apiKeyProviders.map((p) => (
              <ProviderCard
                key={p.id}
                name={p.name}
                authType={p.authType}
                isConnected={p.isConnected}
                {...(p.authDetail !== undefined
                  ? { authDetail: p.authDetail }
                  : {})}
                {...(p.models !== undefined ? { models: p.models } : {})}
              />
            ))}
          </div>

          <div
            style={{
              ...subgroupLabelStyle,
              borderTop: `1px dashed ${theme.colors.borderGray}`,
              paddingTop: 16,
            }}
          >
            {"\u2193"} Subscription / OAuth
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 12,
              marginBottom: 24,
            }}
          >
            {subscriptionProviders.map((p) => (
              <ProviderCard
                key={p.id}
                name={p.name}
                authType={p.authType}
                isConnected={p.isConnected}
                {...(p.authDetail !== undefined
                  ? { authDetail: p.authDetail }
                  : {})}
              />
            ))}
          </div>

          <div
            style={{
              ...subgroupLabelStyle,
              marginBottom: 12,
              borderTop: `1px dashed ${theme.colors.borderGray}`,
              paddingTop: 16,
            }}
          >
            Per-agent model assignment
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              gap: 12,
            }}
          >
            {(["analyzer", "reviewer", "risk_manager"] as const).map(
              (agentId) => {
                const assignment = MOCK_AGENT_MODELS[agentId];
                return (
                  <div key={agentId}>
                    <div
                      style={{
                        fontSize: 13,
                        color: theme.colors.coolGray,
                        marginBottom: 4,
                      }}
                    >
                      {AGENT_LABELS[agentId]}
                    </div>
                    <div
                      style={{
                        border: `1px solid ${theme.colors.borderGray}`,
                        padding: "10px 12px",
                        borderRadius: 8,
                        fontSize: 13,
                      }}
                    >
                      <div style={{ fontWeight: theme.font.weights.medium }}>
                        {assignment.modelId}
                      </div>
                      <div
                        style={{
                          fontSize: 10,
                          color: theme.colors.green,
                          marginTop: 2,
                        }}
                      >
                        via {assignment.providerId}
                      </div>
                    </div>
                  </div>
                );
              },
            )}
          </div>
        </div>

        {/* Trading Thresholds section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>{"\u26A1"} Trading Thresholds</div>
          <div style={sectionSubtitleStyle}>When to trigger a signal</div>
          <table style={{ width: "100%", fontSize: 13 }}>
            <tbody>
              {thresholdRows.map((row) => (
                <tr
                  key={row.label}
                  style={{
                    borderBottom: `1px solid ${theme.colors.rowDivider}`,
                  }}
                >
                  <td
                    style={{
                      padding: "10px 0",
                      color: theme.colors.coolGray,
                    }}
                  >
                    {row.label}
                  </td>
                  <td
                    style={{
                      textAlign: "right",
                      fontWeight: theme.font.weights.medium,
                    }}
                  >
                    {row.value}
                    {row.autoApplied && (
                      <span
                        style={{
                          background: theme.colors.greenSubtle,
                          color: theme.colors.greenDark,
                          padding: "2px 6px",
                          borderRadius: 4,
                          fontSize: 10,
                          marginLeft: 6,
                        }}
                      >
                        auto-applied
                      </span>
                    )}
                  </td>
                  <td style={{ textAlign: "right", width: 80 }}>
                    {row.locked ? (
                      <span
                        style={{
                          color: theme.colors.silverBlue,
                          fontSize: 12,
                        }}
                      >
                        locked
                      </span>
                    ) : (
                      <span
                        style={{
                          color: theme.colors.purple,
                          fontSize: 12,
                          cursor: "pointer",
                        }}
                      >
                        edit
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Risk Limits section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>
            {"\u{1F6E1}\uFE0F"} Risk Limits
          </div>
          <div style={sectionSubtitleStyle}>
            Hard caps on capital and exits
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 16,
              fontSize: 13,
            }}
          >
            {riskRows.map(([label, value]) => (
              <div key={label}>
                <div style={{ color: theme.colors.coolGray }}>{label}</div>
                <div
                  style={{
                    fontWeight: theme.font.weights.semibold,
                    fontSize: 16,
                  }}
                >
                  {value}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Pending Proposals section */}
        <div
          style={{
            background: theme.colors.white,
            border: `2px solid ${theme.colors.purple}`,
            borderRadius: 12,
            padding: 24,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <div
              style={{
                fontSize: 18,
                fontWeight: theme.font.weights.semibold,
              }}
            >
              {"\u{1F4DD}"} Pending Filter Proposals ({proposals.length})
            </div>
            <div style={{ fontSize: 12, color: theme.colors.silverBlue }}>
              From Reviewer
            </div>
          </div>
          <div
            style={{
              fontSize: 13,
              color: theme.colors.silverBlue,
              marginBottom: 16,
            }}
          >
            Reviewer's data-driven suggestions awaiting your approval
          </div>
          {proposals.length === 0 ? (
            <div
              style={{
                fontSize: 13,
                color: theme.colors.coolGray,
                padding: "16px 0",
              }}
            >
              No pending proposals.
            </div>
          ) : (
            proposals.map((p) => (
              <ProposalCard
                key={p.id}
                field={p.field}
                oldValue={p.oldValue}
                proposedValue={p.proposedValue}
                rationale={p.rationale}
                onApprove={() => handleApprove(p.id)}
                onReject={() => handleReject(p.id)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
