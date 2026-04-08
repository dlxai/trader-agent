import React, { useEffect, useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { ProviderCard } from "../components/ProviderCard.js";
import { ProposalCard } from "../components/ProposalCard.js";
import { useSettings } from "../stores/settings.js";
import { pmt, isElectron } from "../ipc-client.js";

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
  const providers = useSettings((s) => s.providers);
  const agentModels = useSettings((s) => s.agentModels);
  const thresholds = useSettings((s) => s.thresholds);
  const riskLimits = useSettings((s) => s.riskLimits);
  const proposals = useSettings((s) => s.pendingProposals);

  // Proxy configuration state
  const [proxyEnabled, setProxyEnabled] = useState(false);
  const [httpProxy, setHttpProxy] = useState("");
  const [httpsProxy, setHttpsProxy] = useState("");
  const [proxySaved, setProxySaved] = useState(false);

  useEffect(() => {
    void useSettings.getState().refresh();
    // Load proxy config
    if (isElectron()) {
      pmt.getProxyConfig().then((config) => {
        setProxyEnabled(config.enabled);
        setHttpProxy(config.httpProxy || "");
        setHttpsProxy(config.httpsProxy || "");
      }).catch(() => {
        // Ignore errors
      });
    }
  }, []);

  const handleApprove = async (id: number) => {
    useSettings.getState().removeProposalLocally(id);
    if (isElectron()) {
      try {
        await pmt.approveProposal(id);
      } finally {
        void useSettings.getState().refresh();
      }
    }
  };

  const handleReject = async (id: number) => {
    useSettings.getState().removeProposalLocally(id);
    if (isElectron()) {
      try {
        await pmt.rejectProposal(id);
      } finally {
        void useSettings.getState().refresh();
      }
    }
  };

  const handleSaveProxy = async () => {
    if (isElectron()) {
      await pmt.setProxyConfig({
        enabled: proxyEnabled,
        httpProxy,
        httpsProxy,
      });
      setProxySaved(true);
      setTimeout(() => setProxySaved(false), 2000);
    }
  };

  const apiKeyProviders = providers.filter((p) => p.authType === "api_key");
  const subscriptionProviders = providers.filter(
    (p) => p.authType === "oauth" || p.authType === "cli_credential",
  );

  const thresholdRows: Array<{
    label: string;
    value: string;
    locked: boolean;
    autoApplied?: boolean;
  }> = [
    { label: "Min trade size", value: `$${thresholds.minTradeUsdc}`, locked: false },
    {
      label: "Min net flow (1m)",
      value: `$${thresholds.minNetFlow1m}`,
      locked: false,
      autoApplied: true,
    },
    {
      label: "Min unique traders (1m)",
      value: `${thresholds.minUniqueTraders1m}`,
      locked: false,
    },
    {
      label: "Min price move (5m)",
      value: `${(thresholds.minPriceMove5m * 100).toFixed(1)}%`,
      locked: false,
    },
    { label: "Min liquidity", value: `$${thresholds.minLiquidity}`, locked: false },
    {
      label: "Dead zone",
      value: `[${thresholds.deadZoneMin}, ${thresholds.deadZoneMax}]`,
      locked: true,
    },
  ];

  const riskRows: Array<[string, string]> = [
    ["Total capital", `$${riskLimits.totalCapital.toLocaleString()}`],
    ["Max position size", `$${riskLimits.maxPositionUsdc}`],
    ["Max single-trade loss", `$${riskLimits.maxSingleLoss}`],
    ["Max open positions", `${riskLimits.maxOpenPositions}`],
    [
      "Daily halt threshold",
      `${(riskLimits.dailyHaltPct * 100).toFixed(1)}%`,
    ],
    [
      "Take profit / Stop loss",
      `+${(riskLimits.takeProfitPct * 100).toFixed(0)}% / -${(riskLimits.stopLossPct * 100).toFixed(0)}%`,
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
                const assignment = agentModels[agentId];
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

        {/* Proxy Configuration section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>🌐 Proxy Configuration</div>
          <div style={sectionSubtitleStyle}>
            Configure proxy for WebSocket connections to Polymarket
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={proxyEnabled}
                onChange={(e) => setProxyEnabled(e.target.checked)}
                style={{ marginRight: 8 }}
              />
              <span>Enable Proxy</span>
            </label>
          </div>
          {proxyEnabled && (
            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>
                  HTTP Proxy
                </label>
                <input
                  type="text"
                  value={httpProxy}
                  onChange={(e) => setHttpProxy(e.target.value)}
                  placeholder="http://127.0.0.1:7890"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: `1px solid ${theme.colors.borderGray}`,
                    borderRadius: 6,
                    fontSize: 14,
                  }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>
                  HTTPS Proxy
                </label>
                <input
                  type="text"
                  value={httpsProxy}
                  onChange={(e) => setHttpsProxy(e.target.value)}
                  placeholder="http://127.0.0.1:7890"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    border: `1px solid ${theme.colors.borderGray}`,
                    borderRadius: 6,
                    fontSize: 14,
                  }}
                />
              </div>
            </div>
          )}
          <div style={{ marginTop: 16 }}>
            <button
              onClick={() => void handleSaveProxy()}
              style={{
                background: theme.colors.purple,
                color: theme.colors.white,
                border: "none",
                borderRadius: 6,
                padding: "8px 16px",
                fontSize: 14,
                fontWeight: theme.font.weights.medium,
                cursor: "pointer",
              }}
            >
              {proxySaved ? "✓ Saved" : "Save Proxy Settings"}
            </button>
          </div>
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
                onApprove={() => {
                  void handleApprove(p.id);
                }}
                onReject={() => {
                  void handleReject(p.id);
                }}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
