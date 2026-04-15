import React, { useEffect, useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
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

const AGENT_LABELS: Record<"analyzer" | "reviewer" | "risk_manager" | "position_evaluator", string> = {
  analyzer: "\u{1F9E0} Analyzer",
  reviewer: "\u{1F4CA} Reviewer",
  risk_manager: "\u{1F6E1}\uFE0F Risk Mgr",
  position_evaluator: "\u{1F4CB} Position Eval",
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
  const liveTradeSettings = useSettings((s) => s.liveTradeSettings);
  const aiExitSettings = useSettings((s) => s.aiExitSettings);
  const drawdownGuardSettings = useSettings((s) => s.drawdownGuardSettings);
  const coordinatorSettings = useSettings((s) => s.coordinatorSettings);
  const updateLiveTradeSettings = useSettings((s) => s.updateLiveTradeSettings);
  const updateAiExitSettings = useSettings((s) => s.updateAiExitSettings);
  const updateDrawdownGuardSettings = useSettings((s) => s.updateDrawdownGuardSettings);
  const updateCoordinatorSettings = useSettings((s) => s.updateCoordinatorSettings);

  // Proxy configuration state - default enabled with common proxy address
  const [proxyEnabled, setProxyEnabled] = useState(true);
  const [httpProxy, setHttpProxy] = useState("http://127.0.0.1:7890");
  const [httpsProxy, setHttpsProxy] = useState("http://127.0.0.1:7890");
  const [proxySaved, setProxySaved] = useState(false);

  // Model config modal state (nofx-style 2-step wizard)
  const [showModelModal, setShowModelModal] = useState(false);
  const [modalStep, setModalStep] = useState<0 | 1>(0); // 0=select provider, 1=configure
  const [selectedProvider, setSelectedProvider] = useState<ProviderInfoUI | null>(null);
  const [editingProvider, setEditingProvider] = useState<ProviderInfoUI | null>(null); // non-null = edit mode
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [baseUrlInput, setBaseUrlInput] = useState("");
  const [modelNameInput, setModelNameInput] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Log viewer state
  const [logDir, setLogDir] = useState<string>("");
  const [latestLogs, setLatestLogs] = useState<string>("");
  const [showLogViewer, setShowLogViewer] = useState(false);

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

      // Load log directory
      pmt.getLogDir().then((dir) => {
        console.log("[SettingsPage] Log dir loaded:", dir);
        setLogDir(dir || "No log directory");
      }).catch((err) => {
        console.error("[SettingsPage] Failed to load log dir:", err);
        setLogDir("Error loading log directory");
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

  const openAddModelModal = () => {
    setShowModelModal(true);
    setModalStep(0);
    setSelectedProvider(null);
    setEditingProvider(null);
    setApiKeyInput("");
    setBaseUrlInput("");
    setModelNameInput("");
    setConnectError(null);
  };

  const openEditModelModal = (provider: ProviderInfoUI) => {
    setShowModelModal(true);
    setModalStep(1);
    setSelectedProvider(provider);
    setEditingProvider(provider);
    setApiKeyInput("");
    setBaseUrlInput("");
    setModelNameInput("");
    setConnectError(null);
  };

  const handleSelectProvider = (provider: ProviderInfoUI) => {
    setSelectedProvider(provider);
    setModalStep(1);
    setConnectError(null);
  };

  const handleSaveModel = async () => {
    console.log("[SettingsPage] handleSaveModel called", { selectedProvider: selectedProvider?.id, apiKeyLength: apiKeyInput.length });
    alert("handleSaveModel called!");
    if (!selectedProvider) {
      console.log("[SettingsPage] no selectedProvider, returning");
      return;
    }
    if (selectedProvider.authType !== "cli_credential" && !apiKeyInput.trim()) {
      console.log("[SettingsPage] no apiKey, setting error");
      setConnectError("API Key / Token is required");
      return;
    }
    if (selectedProvider.authType === "cli_credential" && !baseUrlInput.trim()) {
      console.log("[SettingsPage] no baseUrl for cli_credential, setting error");
      setConnectError("Base URL is required");
      return;
    }
    console.log("[SettingsPage] setting connecting=true");
    setConnecting(true);
    setConnectError(null);
    try {
      const credentials: { apiKey?: string; baseUrl?: string } = {};
      if (apiKeyInput.trim()) credentials.apiKey = apiKeyInput.trim();
      if (baseUrlInput.trim()) credentials.baseUrl = baseUrlInput.trim();
      console.log("[SettingsPage] calling connectProvider with", selectedProvider.id);
      await connectProvider(selectedProvider.id, credentials);
      console.log("[SettingsPage] connectProvider succeeded, closing modal");
      setShowModelModal(false);
    } catch (err) {
      console.log("[SettingsPage] connectProvider error:", err);
      setConnectError(String(err));
    } finally {
      console.log("[SettingsPage] setting connecting=false");
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

  const handleOpenLogDir = async () => {
    if (isElectron()) {
      await pmt.openLogDir();
    }
  };

  const handleViewLogs = async () => {
    if (isElectron()) {
      const logs = await pmt.getLatestLogs(200);
      setLatestLogs(logs || "No logs available yet.");
      setShowLogViewer(true);
    }
  };

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

        {/* LLM Providers section - nofx style */}
        <div style={sectionCardStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <div>
              <div style={sectionTitleStyle}>{"\u{1F916}"} AI Models</div>
              <div style={{ fontSize: 13, color: theme.colors.silverBlue }}>
                {providers.filter(p => p.isConnected).length} models configured
              </div>
            </div>
            <button
              onClick={openAddModelModal}
              style={{
                background: theme.colors.purple,
                color: theme.colors.white,
                border: "none",
                borderRadius: 8,
                padding: "10px 20px",
                fontSize: 14,
                fontWeight: theme.font.weights.medium,
                cursor: "pointer",
              }}
            >
              + Add Model
            </button>
          </div>

          {/* Configured models list */}
          {providers.filter(p => p.isConnected).length === 0 ? (
            <div style={{ textAlign: "center", padding: "40px 0", color: theme.colors.coolGray, fontSize: 14 }}>
              No AI models configured yet. Click "Add Model" to get started.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {providers.filter(p => p.isConnected).map((p) => (
                <div
                  key={p.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "12px 16px",
                    border: `1px solid ${theme.colors.borderGray}`,
                    borderRadius: 10,
                    cursor: "pointer",
                    transition: "border-color 0.15s",
                  }}
                  onClick={() => openEditModelModal(p)}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = theme.colors.purple; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = theme.colors.borderGray; }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: theme.colors.purpleBg,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 18,
                    }}>
                      {"\u{1F916}"}
                    </div>
                    <div>
                      <div style={{ fontWeight: theme.font.weights.semibold, fontSize: 14 }}>{p.name}</div>
                      <div style={{ fontSize: 12, color: theme.colors.coolGray }}>
                        {(p.models && p.models.length > 0) ? p.models.slice(0, 3).join(", ") : "Connected"}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{
                      fontSize: 12,
                      padding: "3px 10px",
                      borderRadius: 12,
                      background: "#ecfdf5",
                      color: "#059669",
                      fontWeight: theme.font.weights.medium,
                    }}>
                      Active
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); void handleDisconnectProvider(p.id); }}
                      style={{
                        background: "transparent",
                        border: `1px solid ${theme.colors.borderGray}`,
                        borderRadius: 6,
                        padding: "4px 10px",
                        fontSize: 12,
                        cursor: "pointer",
                        color: "#e53e3e",
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Per-agent model assignment */}
          {providers.filter(p => p.isConnected).length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ ...subgroupLabelStyle, borderTop: `1px dashed ${theme.colors.borderGray}`, paddingTop: 16 }}>
                Per-agent model assignment
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 12 }}>
                {(["analyzer", "reviewer", "risk_manager", "position_evaluator"] as const).map(
                  (agentId) => {
                    const assignment = agentModels[agentId] || { providerId: "", modelId: "" };
                    const connectedProviders = providers.filter(p => p.isConnected);
                    return (
                      <div key={agentId}>
                        <div style={{ fontSize: 13, color: theme.colors.coolGray, marginBottom: 4 }}>
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
                              <option key={`${provider.id}:${model}`} value={`${provider.id}:${model}`}>
                                {provider.name} · {model}
                              </option>
                            ))
                          )}
                        </select>
                      </div>
                    );
                  }
                )}
              </div>
            </div>
          )}
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

        {/* Log Files section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>📄 Log Files</div>
          <div style={sectionSubtitleStyle}>
            Application logs are automatically saved to disk for debugging
          </div>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>
              Log Directory
            </div>
            <div
              style={{
                fontSize: 13,
                fontFamily: "monospace",
                background: theme.colors.fafafa,
                padding: "8px 12px",
                borderRadius: 6,
                border: `1px solid ${theme.colors.borderGray}`,
                wordBreak: "break-all",
              }}
            >
              {logDir || "Loading..."}
            </div>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={() => void handleViewLogs()}
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
              View Latest Logs
            </button>
            <button
              onClick={() => void handleOpenLogDir()}
              style={{
                background: "transparent",
                border: `1px solid ${theme.colors.borderGray}`,
                borderRadius: 6,
                padding: "8px 16px",
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              Open Log Folder
            </button>
          </div>
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

        {/* Trading Section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>Trading Mode</div>
          <div style={sectionSubtitleStyle}>Configure live vs paper trading and order execution settings</div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={liveTradeSettings.mode === "live"}
                onChange={(e) => void updateLiveTradeSettings({ mode: e.target.checked ? "live" : "paper" })}
                style={{ marginRight: 8 }}
              />
              <span style={{ fontWeight: theme.font.weights.medium }}>
                Live Trading {liveTradeSettings.mode === "live"
                  ? <span style={{ color: "#e53e3e", fontSize: 12, marginLeft: 4 }}>(LIVE - Real Money)</span>
                  : <span style={{ color: theme.colors.coolGray, fontSize: 12, marginLeft: 4 }}>(Paper)</span>}
              </span>
            </label>
          </div>

          {/* Wallet Credentials (only shown in live mode) */}
          {liveTradeSettings.mode === "live" && (
            <div style={{ marginBottom: 16, padding: 12, background: "#fff5f5", borderRadius: 8, border: "1px solid #fed7d7" }}>
              <div style={{ fontSize: 12, color: "#e53e3e", fontWeight: theme.font.weights.bold, marginBottom: 8 }}>
                Wallet Credentials (stored securely in OS keychain)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>Wallet Private Key</div>
                  <input
                    type="password"
                    placeholder="0x..."
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      border: `1px solid ${theme.colors.borderGray}`,
                      borderRadius: 6,
                      fontSize: 13,
                      fontFamily: "monospace",
                      boxSizing: "border-box",
                    }}
                    onBlur={(e) => {
                      const val = e.target.value.trim();
                      if (val) {
                        void updateLiveTradeSettings({ privateKey: val } as any);
                        e.target.value = "";
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        (e.target as HTMLInputElement).blur();
                      }
                    }}
                  />
                  <div style={{ fontSize: 11, color: theme.colors.coolGray, marginTop: 2 }}>
                    Enter and press Tab/Enter to save. Value is not displayed after saving.
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>Proxy Funder Address</div>
                  <input
                    type="text"
                    placeholder="0x... (Polymarket proxy wallet address)"
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      border: `1px solid ${theme.colors.borderGray}`,
                      borderRadius: 6,
                      fontSize: 13,
                      fontFamily: "monospace",
                      boxSizing: "border-box",
                    }}
                    onBlur={(e) => {
                      const val = e.target.value.trim();
                      if (val) {
                        void updateLiveTradeSettings({ funderAddress: val } as any);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        (e.target as HTMLInputElement).blur();
                      }
                    }}
                  />
                  <div style={{ fontSize: 11, color: theme.colors.coolGray, marginTop: 2 }}>
                    Your Polymarket proxy contract address (signature_type=2)
                  </div>
                </div>
              </div>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, fontSize: 13 }}>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Slippage Threshold (%)</div>
              <EditableField
                label="Slippage Threshold"
                value={(liveTradeSettings.slippageThreshold * 100).toFixed(1)}
                onSave={(v) => void updateLiveTradeSettings({ slippageThreshold: v / 100 })}
                suffix="%"
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Max Slippage (%)</div>
              <EditableField
                label="Max Slippage"
                value={(liveTradeSettings.maxSlippage * 100).toFixed(1)}
                onSave={(v) => void updateLiveTradeSettings({ maxSlippage: v / 100 })}
                suffix="%"
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Limit Order Timeout (s)</div>
              <EditableField
                label="Limit Order Timeout"
                value={liveTradeSettings.limitOrderTimeoutSec}
                onSave={(v) => void updateLiveTradeSettings({ limitOrderTimeoutSec: v })}
                suffix=" s"
              />
            </div>
          </div>
        </div>

        {/* AI Position Evaluator Section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>AI Position Evaluator</div>
          <div style={sectionSubtitleStyle}>Periodically re-evaluate open positions using AI analysis</div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={aiExitSettings.enabled}
                onChange={(e) => void updateAiExitSettings({ enabled: e.target.checked })}
                style={{ marginRight: 8 }}
              />
              <span style={{ fontWeight: theme.font.weights.medium }}>Enable AI Exit Evaluator</span>
            </label>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16, fontSize: 13 }}>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Evaluation Interval (seconds)</div>
              <EditableField
                label="Interval"
                value={aiExitSettings.intervalSec}
                onSave={(v) => void updateAiExitSettings({ intervalSec: v })}
                suffix=" s"
              />
            </div>
          </div>
        </div>

        {/* Coordinator Section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>Coordinator</div>
          <div style={sectionSubtitleStyle}>Controls how the coordinator agent operates and takes actions</div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={coordinatorSettings.actionable}
                onChange={(e) => void updateCoordinatorSettings({ actionable: e.target.checked })}
                style={{ marginRight: 8 }}
              />
              <span style={{ fontWeight: theme.font.weights.medium }}>Allow Coordinator Actions</span>
            </label>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16, fontSize: 13 }}>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Run Interval (minutes)</div>
              <EditableField
                label="Interval"
                value={coordinatorSettings.intervalMin}
                onSave={(v) => void updateCoordinatorSettings({ intervalMin: v })}
                suffix=" min"
              />
            </div>
          </div>
        </div>

        {/* Drawdown Guard Section */}
        <div style={sectionCardStyle}>
          <div style={sectionTitleStyle}>Drawdown Guard</div>
          <div style={sectionSubtitleStyle}>Protect profits by limiting drawdown from peak equity</div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", cursor: "pointer", marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={drawdownGuardSettings.enabled}
                onChange={(e) => void updateDrawdownGuardSettings({ enabled: e.target.checked })}
                style={{ marginRight: 8 }}
              />
              <span style={{ fontWeight: theme.font.weights.medium }}>Enable Drawdown Guard</span>
            </label>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 13 }}>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Min Profit Threshold (%)</div>
              <EditableField
                label="Min Profit"
                value={(drawdownGuardSettings.minProfitPct * 100).toFixed(1)}
                onSave={(v) => void updateDrawdownGuardSettings({ minProfitPct: v / 100 })}
                suffix="%"
              />
            </div>
            <div>
              <div style={{ color: theme.colors.coolGray, marginBottom: 4 }}>Max Drawdown from Peak (%)</div>
              <EditableField
                label="Max Drawdown"
                value={(drawdownGuardSettings.maxDrawdownFromPeak * 100).toFixed(1)}
                onSave={(v) => void updateDrawdownGuardSettings({ maxDrawdownFromPeak: v / 100 })}
                suffix="%"
              />
            </div>
          </div>
        </div>

        {/* Custom LLM Endpoints removed per user request */}

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

        {/* Log Viewer Dialog */}
        {showLogViewer && (
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
                setShowLogViewer(false);
              }
            }}
          >
            <div
              style={{
                background: theme.colors.white,
                borderRadius: 12,
                padding: 24,
                width: 900,
                maxWidth: "95vw",
                height: "80vh",
                display: "flex",
                flexDirection: "column",
                boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
              }}
            >
              <div
                style={{
                  fontSize: 18,
                  fontWeight: theme.font.weights.semibold,
                  marginBottom: 16,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span>Latest Application Logs</span>
                <button
                  onClick={() => setShowLogViewer(false)}
                  style={{
                    background: "transparent",
                    border: "none",
                    fontSize: 20,
                    cursor: "pointer",
                    color: theme.colors.coolGray,
                  }}
                >
                  ×
                </button>
              </div>
              <div
                style={{
                  flex: 1,
                  overflow: "auto",
                  background: "#1a1a2e",
                  borderRadius: 8,
                  padding: 16,
                  fontFamily: "monospace",
                  fontSize: 12,
                  color: "#e0e0e0",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {latestLogs || "No logs available yet."}
              </div>
              <div style={{ marginTop: 16, display: "flex", gap: 12, justifyContent: "flex-end" }}>
                <button
                  onClick={() => void handleViewLogs()}
                  style={{
                    background: theme.colors.purple,
                    color: theme.colors.white,
                    border: "none",
                    borderRadius: 6,
                    padding: "8px 16px",
                    fontSize: 14,
                    cursor: "pointer",
                  }}
                >
                  Refresh
                </button>
                <button
                  onClick={() => setShowLogViewer(false)}
                  style={{
                    background: "transparent",
                    border: `1px solid ${theme.colors.borderGray}`,
                    borderRadius: 6,
                    padding: "8px 16px",
                    fontSize: 14,
                    cursor: "pointer",
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Model Config Modal (nofx-style 2-step wizard) */}
        {showModelModal && (
          <div
            style={{
              position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
              background: "rgba(0, 0, 0, 0.5)",
              display: "flex", alignItems: "center", justifyContent: "center",
              zIndex: 1000,
            }}
            onClick={(e) => { if (e.target === e.currentTarget) setShowModelModal(false); }}
          >
            <div style={{
              background: theme.colors.white,
              borderRadius: 12,
              padding: 24,
              width: modalStep === 0 ? 640 : 440,
              maxWidth: "90vw",
              maxHeight: "80vh",
              overflowY: "auto",
              boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
            }}>
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {modalStep === 1 && !editingProvider && (
                    <button
                      onClick={() => setModalStep(0)}
                      style={{ background: "transparent", border: "none", fontSize: 18, cursor: "pointer", padding: "0 4px" }}
                    >
                      ←
                    </button>
                  )}
                  <span style={{ fontSize: 18, fontWeight: theme.font.weights.semibold }}>
                    {modalStep === 0 ? "Select AI Provider" : editingProvider ? `Edit ${selectedProvider?.name}` : `Configure ${selectedProvider?.name}`}
                  </span>
                </div>
                <button
                  onClick={() => setShowModelModal(false)}
                  style={{ background: "transparent", border: "none", fontSize: 20, cursor: "pointer", color: theme.colors.coolGray }}
                >
                  ×
                </button>
              </div>

              {/* Step 0: Provider Selection Grid */}
              {modalStep === 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                  {providers.filter(p => !p.isConnected).map((p) => (
                    <div
                      key={p.id}
                      onClick={() => handleSelectProvider(p)}
                      style={{
                        border: `2px solid ${theme.colors.borderGray}`,
                        borderRadius: 10,
                        padding: "16px 12px",
                        textAlign: "center",
                        cursor: "pointer",
                        transition: "border-color 0.15s, background 0.15s",
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLDivElement).style.borderColor = theme.colors.purple;
                        (e.currentTarget as HTMLDivElement).style.background = theme.colors.purpleBg;
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLDivElement).style.borderColor = theme.colors.borderGray;
                        (e.currentTarget as HTMLDivElement).style.background = "transparent";
                      }}
                    >
                      <div style={{ fontSize: 24, marginBottom: 6 }}>{"\u{1F916}"}</div>
                      <div style={{ fontSize: 13, fontWeight: theme.font.weights.semibold }}>{p.name}</div>
                      <div style={{
                        fontSize: 11,
                        color: theme.colors.coolGray,
                        marginTop: 2,
                      }}>
                        {p.authType === "cli_credential" ? "Local" : "API Key"}
                      </div>
                    </div>
                  ))}
                  {providers.filter(p => !p.isConnected).length === 0 && (
                    <div style={{ gridColumn: "1 / -1", textAlign: "center", padding: 20, color: theme.colors.coolGray }}>
                      All providers are already configured.
                    </div>
                  )}
                </div>
              )}

              {/* Step 1: Configuration Form */}
              {modalStep === 1 && selectedProvider && (
                <div>
                  {/* API Key field - for all except cli_credential */}
                  {selectedProvider.authType !== "cli_credential" && (
                    <div style={{ marginBottom: 16 }}>
                      <label style={{ display: "block", fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>
                        API Key / Token *
                      </label>
                      <input
                        type="password"
                        value={apiKeyInput}
                        onChange={(e) => setApiKeyInput(e.target.value)}
                        placeholder="Enter your API key or token"
                        autoFocus
                        style={{
                          width: "100%", padding: "10px 12px",
                          border: `1px solid ${theme.colors.borderGray}`,
                          borderRadius: 6, fontSize: 14, boxSizing: "border-box",
                        }}
                      />
                    </div>
                  )}

                  {/* Base URL field - for cli_credential (required) or as optional override */}
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: "block", fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>
                      {selectedProvider.authType === "cli_credential" ? "Base URL *" : "Custom Base URL (optional)"}
                    </label>
                    <input
                      type="url"
                      value={baseUrlInput}
                      onChange={(e) => setBaseUrlInput(e.target.value)}
                      placeholder={selectedProvider.authType === "cli_credential" ? "http://localhost:11434" : "Leave blank for default"}
                      autoFocus={selectedProvider.authType === "cli_credential"}
                      style={{
                        width: "100%", padding: "10px 12px",
                        border: `1px solid ${theme.colors.borderGray}`,
                        borderRadius: 6, fontSize: 14, boxSizing: "border-box",
                      }}
                    />
                    <div style={{ fontSize: 11, color: theme.colors.coolGray, marginTop: 2 }}>
                      {selectedProvider.authType === "cli_credential" ? "URL of your local service" : "Override the default API endpoint (for proxies or compatible services)"}
                    </div>
                  </div>

                  {/* Custom model name - optional */}
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: "block", fontSize: 12, color: theme.colors.coolGray, marginBottom: 4 }}>
                      Custom Model Name (optional)
                    </label>
                    <input
                      type="text"
                      value={modelNameInput}
                      onChange={(e) => setModelNameInput(e.target.value)}
                      placeholder="Leave blank for default model"
                      style={{
                        width: "100%", padding: "10px 12px",
                        border: `1px solid ${theme.colors.borderGray}`,
                        borderRadius: 6, fontSize: 14, boxSizing: "border-box",
                      }}
                    />
                  </div>

                  {/* Error message */}
                  {connectError && (
                    <div style={{
                      background: "#fee2e2", color: "#dc2626",
                      padding: "10px 12px", borderRadius: 6, fontSize: 13, marginBottom: 16,
                    }}>
                      {connectError}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
                    {editingProvider && (
                      <button
                        onClick={() => { void handleDisconnectProvider(editingProvider.id); setShowModelModal(false); }}
                        style={{
                          background: "transparent", border: `1px solid #e53e3e`,
                          borderRadius: 6, padding: "8px 16px", fontSize: 14,
                          cursor: "pointer", color: "#e53e3e", marginRight: "auto",
                        }}
                      >
                        Delete
                      </button>
                    )}
                    <button
                      onClick={() => setShowModelModal(false)}
                      style={{
                        background: "transparent", border: `1px solid ${theme.colors.borderGray}`,
                        borderRadius: 6, padding: "8px 16px", fontSize: 14, cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => void handleSaveModel()}
                      disabled={connecting}
                      style={{
                        background: theme.colors.purple, color: theme.colors.white,
                        border: "none", borderRadius: 6, padding: "8px 20px",
                        fontSize: 14, fontWeight: theme.font.weights.medium,
                        cursor: connecting ? "not-allowed" : "pointer",
                        opacity: connecting ? 0.6 : 1,
                      }}
                    >
                      {connecting ? "Connecting..." : "Save Config"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
