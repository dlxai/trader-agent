import React, { useEffect, useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { ProviderCard } from "../components/ProviderCard.js";
import { ProposalCard } from "../components/ProposalCard.js";
import { useSettings, type ProviderInfoUI } from "../stores/settings.js";
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

// Editable field component
function EditableField({
  label,
  value,
  onSave,
  suffix = "",
  type = "number",
}: {
  label: string;
  value: string | number;
  onSave: (val: number) => void;
  suffix?: string;
  type?: "number" | "percent";
}) {
  const [editing, setEditing] = useState(false);
  const [inputValue, setInputValue] = useState(String(value));

  const handleSave = () => {
    const num = type === "percent" ? parseFloat(inputValue) / 100 : parseFloat(inputValue);
    if (!isNaN(num)) {
      onSave(num);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="number"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          autoFocus
          style={{
            width: 100,
            padding: "4px 8px",
            border: `1px solid ${theme.colors.purple}`,
            borderRadius: 4,
            fontSize: 13,
          }}
        />
        <span style={{ fontSize: 12, color: theme.colors.coolGray }}>{suffix}</span>
        <button
          onClick={handleSave}
          style={{
            background: theme.colors.purple,
            color: theme.colors.white,
            border: "none",
            borderRadius: 4,
            padding: "4px 8px",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          Save
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontWeight: theme.font.weights.medium }}>
        {value}{suffix}
      </span>
      <button
        onClick={() => setEditing(true)}
        style={{
          background: "transparent",
          border: "none",
          color: theme.colors.purple,
          fontSize: 12,
          cursor: "pointer",
          padding: "2px 6px",
        }}
      >
        Edit
      </button>
    </div>
  );
}

export function SettingsPage() {
  const providers = useSettings((s) => s.providers);
  const agentModels = useSettings((s) => s.agentModels);
  const thresholds = useSettings((s) => s.thresholds);
  const riskLimits = useSettings((s) => s.riskLimits);
  const proposals = useSettings((s) => s.pendingProposals);
  const updateThreshold = useSettings((s) => s.updateThreshold);
  const updateRiskLimit = useSettings((s) => s.updateRiskLimit);
  const setAgentModel = useSettings((s) => s.setAgentModel);
  const connectProvider = useSettings((s) => s.connectProvider);
  const disconnectProvider = useSettings((s) => s.disconnectProvider);

  // Proxy configuration state - default enabled with common proxy address
  const [proxyEnabled, setProxyEnabled] = useState(true);
  const [httpProxy, setHttpProxy] = useState("http://127.0.0.1:7890");
  const [httpsProxy, setHttpsProxy] = useState("http://127.0.0.1:7890");
  const [proxySaved, setProxySaved] = useState(false);

  // Provider configuration dialog state
  const [configuringProvider, setConfiguringProvider] = useState<ProviderInfoUI | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [baseUrlInput, setBaseUrlInput] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  useEffect(() => {
    void useSettings.getState().refresh();
    // Load proxy config - use defaults if not configured
    if (isElectron()) {
      pmt.getProxyConfig().then((config) => {
        // If no config saved (all empty), use defaults
        if (!config.httpProxy && !config.httpsProxy) {
          console.log("[SettingsPage] No proxy config found, using defaults");
          const defaultConfig = {
            enabled: true,
            httpProxy: "http://127.0.0.1:7890",
            httpsProxy: "http://127.0.0.1:7890",
          };
          setProxyEnabled(defaultConfig.enabled);
          setHttpProxy(defaultConfig.httpProxy);
          setHttpsProxy(defaultConfig.httpsProxy);
          // Save default config
          pmt.setProxyConfig(defaultConfig).catch(() => {});
        } else {
          setProxyEnabled(config.enabled);
          setHttpProxy(config.httpProxy || "");
          setHttpsProxy(config.httpsProxy || "");
        }
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

  const handleOpenProviderConfig = (provider: ProviderInfoUI) => {
    setConfiguringProvider(provider);
    setApiKeyInput("");
    setBaseUrlInput("");
    setConnectError(null);
  };

  const handleConnectProvider = async () => {
    if (!configuringProvider) return;

    console.log("[SettingsPage] Connecting provider:", configuringProvider.id, "type:", configuringProvider.authType);

    // Validate input based on provider type
    if (configuringProvider.authType === "api_key" && !apiKeyInput.trim()) {
      setConnectError("API key is required");
      return;
    }
    if (configuringProvider.authType === "cli_credential" && !baseUrlInput.trim()) {
      setConnectError("Base URL is required");
      return;
    }

    setConnecting(true);
    setConnectError(null);
    try {
      const credentials: { apiKey?: string; baseUrl?: string } = {};
      if (apiKeyInput.trim()) {
        credentials.apiKey = apiKeyInput.trim();
      }
      if (baseUrlInput.trim()) {
        credentials.baseUrl = baseUrlInput.trim();
      }
      console.log("[SettingsPage] Calling connectProvider with credentials:", { ...credentials, apiKey: credentials.apiKey ? "***" : undefined });
      await connectProvider(configuringProvider.id, credentials);
      console.log("[SettingsPage] Provider connected successfully");
      setConfiguringProvider(null);
    } catch (err) {
      console.error("[SettingsPage] Failed to connect provider:", err);
      setConnectError(String(err));
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnectProvider = async (providerId: string) => {
    try {
      await disconnectProvider(providerId);
    } catch (err) {
      console.error("Failed to disconnect provider:", err);
    }
  };

  const apiKeyProviders = providers.filter((p) => p.authType === "api_key");
  const subscriptionProviders = providers.filter(
    (p) => p.authType === "oauth" || p.authType === "cli_credential",
  );

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
                onConnect={() => handleOpenProviderConfig(p)}
                onDisconnect={() => handleDisconnectProvider(p.id)}
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
            {"\u2193"} Subscription / OAuth / Local
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
                onConnect={() => handleOpenProviderConfig(p)}
                onDisconnect={() => handleDisconnectProvider(p.id)}
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
                const assignment = agentModels[agentId] || { providerId: "", modelId: "" };
                const connectedProviders = providers.filter(p => p.isConnected);
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
                    <select
                      value={`${assignment.providerId}:${assignment.modelId}`}
                      onChange={(e) => {
                        const [providerId, modelId] = e.target.value.split(":");
                        if (providerId && modelId) {
                          void setAgentModel(agentId, providerId, modelId);
                        }
                      }}
                      style={{
                        border: `1px solid ${theme.colors.borderGray}`,
                        padding: "10px 12px",
                        borderRadius: 8,
                        fontSize: 13,
                        width: "100%",
                        background: theme.colors.white,
                      }}
                    >
                      <option value=":">Select model...</option>
                      {connectedProviders.map((provider) =>
                        (provider.models || []).map((model) => (
                          <option
                            key={`${provider.id}:${model}`}
                            value={`${provider.id}:${model}`}
                          >
                            {provider.name} · {model}
                          </option>
                        ))
                      )}
                    </select>
                  </div>
                );
              },
            )}
          </div>
        </div>

        {/* Trading Thresholds section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>{"\u26A1"} Trading Thresholds</div>
          <div style={sectionSubtitleStyle}>When to trigger a signal (click to edit)</div>
          <table style={{ width: "100%", fontSize: 13 }}>
            <tbody>
              <tr style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
                <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>Min trade size</td>
                <td style={{ textAlign: "right" }}>
                  <EditableField
                    label="Min trade"
                    value={thresholds.minTradeUsdc}
                    onSave={(v) => updateThreshold("minTradeUsdc", v)}
                    suffix=" USD"
                  />
                </td>
              </tr>
              <tr style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
                <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>Min net flow (1m)</td>
                <td style={{ textAlign: "right" }}>
                  <EditableField
                    label="Min net flow"
                    value={thresholds.minNetFlow1m}
                    onSave={(v) => updateThreshold("minNetFlow1m", v)}
                    suffix=" USD"
                  />
                </td>
              </tr>
              <tr style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
                <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>Min unique traders (1m)</td>
                <td style={{ textAlign: "right" }}>
                  <EditableField
                    label="Min traders"
                    value={thresholds.minUniqueTraders1m}
                    onSave={(v) => updateThreshold("minUniqueTraders1m", v)}
                    suffix=""
                  />
                </td>
              </tr>
              <tr style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
                <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>Min price move (5m)</td>
                <td style={{ textAlign: "right" }}>
                  <EditableField
                    label="Min price move"
                    value={thresholds.minPriceMove5m}
                    onSave={(v) => updateThreshold("minPriceMove5m", v)}
                    suffix="%"
                    type="percent"
                  />
                </td>
              </tr>
              <tr style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
                <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>Min liquidity</td>
                <td style={{ textAlign: "right" }}>
                  <EditableField
                    label="Min liquidity"
                    value={thresholds.minLiquidity}
                    onSave={(v) => updateThreshold("minLiquidity", v)}
                    suffix=" USD"
                  />
                </td>
              </tr>
              <tr style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
                <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>Dead zone</td>
                <td style={{ textAlign: "right", fontWeight: theme.font.weights.medium }}>
                  [{thresholds.deadZoneMin}, {thresholds.deadZoneMax}]
                  <span style={{ color: theme.colors.silverBlue, fontSize: 12, marginLeft: 8 }}>locked</span>
                </td>
              </tr>
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
            Hard caps on capital and exits (click to edit)
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 16,
              fontSize: 13,
            }}
          >
            <div>
              <div style={{ color: theme.colors.coolGray }}>Total capital</div>
              <EditableField
                label="Total capital"
                value={riskLimits.totalCapital}
                onSave={(v) => updateRiskLimit("totalCapital", v)}
                suffix=""
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray }}>Max position size</div>
              <EditableField
                label="Max position"
                value={riskLimits.maxPositionUsdc}
                onSave={(v) => updateRiskLimit("maxPositionUsdc", v)}
                suffix=" USD"
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray }}>Max single-trade loss</div>
              <EditableField
                label="Max loss"
                value={riskLimits.maxSingleLoss}
                onSave={(v) => updateRiskLimit("maxSingleLoss", v)}
                suffix=" USD"
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray }}>Max open positions</div>
              <EditableField
                label="Max positions"
                value={riskLimits.maxOpenPositions}
                onSave={(v) => updateRiskLimit("maxOpenPositions", v)}
                suffix=""
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray }}>Daily halt threshold</div>
              <EditableField
                label="Daily halt"
                value={riskLimits.dailyHaltPct}
                onSave={(v) => updateRiskLimit("dailyHaltPct", v)}
                suffix="%"
                type="percent"
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray }}>Take profit / Stop loss</div>
              <div style={{ fontWeight: theme.font.weights.semibold, fontSize: 16 }}>
                +{(riskLimits.takeProfitPct * 100).toFixed(0)}% / -{(riskLimits.stopLossPct * 100).toFixed(0)}%
              </div>
            </div>
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

        {/* Provider Configuration Dialog */}
        {configuringProvider && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0, 0, 0, 0.5)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
            }}
            onClick={(e) => {
              if (e.target === e.currentTarget) {
                setConfiguringProvider(null);
              }
            }}
          >
            <div
              style={{
                background: theme.colors.white,
                borderRadius: 12,
                padding: 24,
                width: 400,
                maxWidth: "90vw",
                boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
              }}
            >
              <div
                style={{
                  fontSize: 18,
                  fontWeight: theme.font.weights.semibold,
                  marginBottom: 4,
                }}
              >
                Configure {configuringProvider.name}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: theme.colors.silverBlue,
                  marginBottom: 20,
                }}
              >
                {configuringProvider.authType === "api_key"
                  ? "Enter your API key to connect"
                  : configuringProvider.authType === "cli_credential"
                    ? "Enter the base URL for your local service"
                    : "OAuth configuration"}
              </div>

              {configuringProvider.authType === "api_key" && (
                <div style={{ marginBottom: 16 }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: 12,
                      color: theme.colors.coolGray,
                      marginBottom: 4,
                    }}
                  >
                    API Key
                  </label>
                  <input
                    type="password"
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder="sk-..."
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      border: `1px solid ${theme.colors.borderGray}`,
                      borderRadius: 6,
                      fontSize: 14,
                    }}
                  />
                </div>
              )}

              {configuringProvider.authType === "cli_credential" && (
                <div style={{ marginBottom: 16 }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: 12,
                      color: theme.colors.coolGray,
                      marginBottom: 4,
                    }}
                  >
                    Base URL
                  </label>
                  <input
                    type="text"
                    value={baseUrlInput}
                    onChange={(e) => setBaseUrlInput(e.target.value)}
                    placeholder="http://localhost:11434"
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      border: `1px solid ${theme.colors.borderGray}`,
                      borderRadius: 6,
                      fontSize: 14,
                    }}
                  />
                </div>
              )}

              {connectError && (
                <div
                  style={{
                    background: "#fee2e2",
                    color: "#dc2626",
                    padding: "10px 12px",
                    borderRadius: 6,
                    fontSize: 13,
                    marginBottom: 16,
                  }}
                >
                  {connectError}
                </div>
              )}

              <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
                <button
                  onClick={() => setConfiguringProvider(null)}
                  style={{
                    background: "transparent",
                    border: `1px solid ${theme.colors.borderGray}`,
                    borderRadius: 6,
                    padding: "8px 16px",
                    fontSize: 14,
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleConnectProvider}
                  disabled={connecting}
                  style={{
                    background: theme.colors.purple,
                    color: theme.colors.white,
                    border: "none",
                    borderRadius: 6,
                    padding: "8px 16px",
                    fontSize: 14,
                    fontWeight: theme.font.weights.medium,
                    cursor: connecting ? "not-allowed" : "pointer",
                    opacity: connecting ? 0.6 : 1,
                  }}
                >
                  {connecting ? "Connecting..." : "Connect"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
