import React, { useEffect, useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { KpiCard } from "../components/KpiCard.js";
import { PositionTable } from "../components/PositionTable.js";
import { CoordinatorBanner } from "../components/CoordinatorBanner.js";
import { usePortfolio } from "../stores/portfolio.js";
import { usePositions } from "../stores/positions.js";
import { useCoordinator } from "../stores/coordinator.js";
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

const headerRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  marginBottom: 24,
};

const titleStyle: React.CSSProperties = {
  fontSize: 32,
  fontWeight: theme.font.weights.bold,
  letterSpacing: -1,
};

const subtitleStyle: React.CSSProperties = {
  fontSize: 13,
  color: theme.colors.silverBlue,
  marginTop: 4,
};

const runButtonStyle: React.CSSProperties = {
  background: theme.colors.purple,
  color: theme.colors.white,
  padding: "13px 16px",
  borderRadius: 12,
  fontWeight: theme.font.weights.medium,
  fontSize: 14,
  border: "none",
  cursor: "pointer",
};

const kpiGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(4, 1fr)",
  gap: 16,
  marginBottom: 24,
};

export function DashboardPage() {
  const portfolio = usePortfolio();
  const positions = usePositions((s) => s.positions);
  const coordinator = useCoordinator();
  const pendingProposalCount = useSettings((s) => s.pendingProposals.length);

  // Trading control state
  const [isRunning, setIsRunning] = useState(true);
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState<string>("");
  const [loadingReviewer, setLoadingReviewer] = useState(false);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  // Load initial trading status and logs
  useEffect(() => {
    void usePortfolio.getState().refresh();
    void usePositions.getState().refresh();
    void useCoordinator.getState().refresh();
    if (isElectron()) {
      pmt.getLatestLogs(100).then(setLogs).catch(() => {});
    }
    const interval = setInterval(() => {
      void usePortfolio.getState().refresh();
      void usePositions.getState().refresh();
      void useCoordinator.getState().refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Subscribe to real-time log events
  useEffect(() => {
    if (!isElectron() || !showLogs) return;
    const unsubscribe = pmt.on("log:new", (log: unknown) => {
      setLogs((prev) => prev + "\n" + String(log));
    });
    return unsubscribe;
  }, [showLogs]);

  const handleRunReviewer = async () => {
    if (!isElectron()) return;
    setLoadingReviewer(true);
    try {
      await pmt.triggerReviewerNow();
    } catch (err) {
      console.error("Failed to run reviewer:", err);
    } finally {
      setLoadingReviewer(false);
    }
  };

  const handlePause = async () => {
    if (!isElectron()) return;
    setLoadingAction("pause");
    try {
      await pmt.pauseTrading();
      setIsRunning(false);
    } catch (err) {
      console.error("Failed to pause:", err);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleResume = async () => {
    if (!isElectron()) return;
    setLoadingAction("resume");
    try {
      await pmt.resumeTrading();
      setIsRunning(true);
    } catch (err) {
      console.error("Failed to resume:", err);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleEmergencyStop = async () => {
    if (!isElectron()) return;
    if (!confirm("Are you sure you want to emergency stop? All positions will be closed.")) {
      return;
    }
    setLoadingAction("stop");
    try {
      await pmt.emergencyStop();
      setIsRunning(false);
    } catch (err) {
      console.error("Failed to emergency stop:", err);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRefreshLogs = async () => {
    if (!isElectron()) return;
    const newLogs = await pmt.getLatestLogs(200);
    setLogs(newLogs || "No logs available.");
  };

  const todayPnlPrefix = portfolio.todayPnl >= 0 ? "+" : "-";
  const todayPnlText = `${todayPnlPrefix}$${Math.abs(portfolio.todayPnl).toFixed(2)} today`;

  // Button styles
  const buttonBaseStyle: React.CSSProperties = {
    padding: "10px 14px",
    borderRadius: 12,
    fontWeight: theme.font.weights.medium,
    fontSize: 13,
    border: "none",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: 6,
  };

  const runButton: React.CSSProperties = {
    ...buttonBaseStyle,
    background: theme.colors.purple,
    color: theme.colors.white,
  };

  const pauseButton: React.CSSProperties = {
    ...buttonBaseStyle,
    background: "#f59e0b",
    color: theme.colors.white,
  };

  const resumeButton: React.CSSProperties = {
    ...buttonBaseStyle,
    background: "#10b981",
    color: theme.colors.white,
  };

  const stopButton: React.CSSProperties = {
    ...buttonBaseStyle,
    background: "#ef4444",
    color: theme.colors.white,
  };

  const logsButton: React.CSSProperties = {
    ...buttonBaseStyle,
    background: theme.colors.fafafa,
    border: `1px solid ${theme.colors.borderGray}`,
    color: theme.colors.coolGray,
  };

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={pendingProposalCount} />
      <div style={contentStyle}>
        <div style={headerRowStyle}>
          <div>
            <div style={titleStyle}>Dashboard</div>
            <div style={subtitleStyle}>
              {new Date().toLocaleString()} ·{" "}
              <span style={{ color: isRunning ? "#10b981" : "#ef4444", fontWeight: 500 }}>
                {isRunning ? "● Running" : "● Paused"}
              </span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              style={{ ...runButton, opacity: loadingReviewer ? 0.6 : 1 }}
              onClick={() => void handleRunReviewer()}
              disabled={loadingReviewer}
            >
              {loadingReviewer ? "Running..." : "⚡ Run Reviewer"}
            </button>
            {isRunning ? (
              <button
                type="button"
                style={{ ...pauseButton, opacity: loadingAction === "pause" ? 0.6 : 1 }}
                onClick={() => void handlePause()}
                disabled={loadingAction !== null}
              >
                ⏸ Pause
              </button>
            ) : (
              <button
                type="button"
                style={{ ...resumeButton, opacity: loadingAction === "resume" ? 0.6 : 1 }}
                onClick={() => void handleResume()}
                disabled={loadingAction !== null}
              >
                ▶ Resume
              </button>
            )}
            <button
              type="button"
              style={{ ...stopButton, opacity: loadingAction === "stop" ? 0.6 : 1 }}
              onClick={() => void handleEmergencyStop()}
              disabled={loadingAction !== null}
            >
              ⏹ Stop
            </button>
            <button
              type="button"
              style={{ ...logsButton }}
              onClick={() => {
                setShowLogs(!showLogs);
                if (!showLogs) void handleRefreshLogs();
              }}
            >
              📄 Logs
            </button>
          </div>
        </div>

        <CoordinatorBanner
          summary={coordinator.latestSummary}
          generatedMinutesAgo={coordinator.generatedMinutesAgo}
        />

        <div style={kpiGridStyle}>
          <KpiCard
            label="Equity"
            value={`$${portfolio.equity.toFixed(2)}`}
            subtitle={todayPnlText}
            subtitleColor={portfolio.todayPnl >= 0 ? "green" : "red"}
          />
          <KpiCard
            label="Open positions"
            value={`${portfolio.openPositionCount} / ${portfolio.maxOpenPositions}`}
            subtitle={`Exposure $${portfolio.totalExposure}`}
          />
          <KpiCard
            label="7d Win rate"
            value={`${(portfolio.weeklyWinRate * 100).toFixed(1)}%`}
            subtitle={`${portfolio.weeklyWins} / ${portfolio.weeklyTotal} trades`}
            subtitleColor="green"
          />
          <KpiCard
            label="Drawdown"
            value={`${portfolio.drawdownPct.toFixed(1)}%`}
            subtitle={`From peak $${portfolio.peakEquity}`}
          />
        </div>

        <PositionTable positions={positions} />

        {/* Real-time Logs Panel */}
        {showLogs && (
          <div
            style={{
              position: "fixed",
              bottom: 0,
              left: 220,
              right: 0,
              height: 300,
              background: "#1a1a2e",
              borderTop: `2px solid ${theme.colors.purple}`,
              display: "flex",
              flexDirection: "column",
              zIndex: 100,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 16px",
                background: "#16162a",
                borderBottom: "1px solid #2a2a4a",
              }}
            >
              <span style={{ color: "#e0e0e0", fontWeight: 500 }}>📄 Real-time Logs</span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => void handleRefreshLogs()}
                  style={{
                    background: "transparent",
                    border: "1px solid #4a4a6a",
                    color: "#e0e0e0",
                    padding: "4px 10px",
                    borderRadius: 6,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  Refresh
                </button>
                <button
                  onClick={() => setShowLogs(false)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "#999",
                    fontSize: 18,
                    cursor: "pointer",
                  }}
                >
                  ×
                </button>
              </div>
            </div>
            <div
              style={{
                flex: 1,
                overflow: "auto",
                padding: 12,
                fontFamily: "monospace",
                fontSize: 11,
                color: "#00ff00",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {logs || "No logs available."}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
