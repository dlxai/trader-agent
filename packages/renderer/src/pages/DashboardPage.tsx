import React, { useEffect } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { KpiCard } from "../components/KpiCard.js";
import { PositionTable } from "../components/PositionTable.js";
import { CoordinatorBanner } from "../components/CoordinatorBanner.js";
import { usePortfolio } from "../stores/portfolio.js";
import { usePositions } from "../stores/positions.js";
import { useCoordinator } from "../stores/coordinator.js";
import { useSettings } from "../stores/settings.js";

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

  useEffect(() => {
    void usePortfolio.getState().refresh();
    void usePositions.getState().refresh();
    void useCoordinator.getState().refresh();
    const interval = setInterval(() => {
      void usePortfolio.getState().refresh();
      void usePositions.getState().refresh();
      void useCoordinator.getState().refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const todayPnlPrefix = portfolio.todayPnl >= 0 ? "+" : "-";
  const todayPnlText = `${todayPnlPrefix}$${Math.abs(portfolio.todayPnl).toFixed(2)} today`;

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={pendingProposalCount} />
      <div style={contentStyle}>
        <div style={headerRowStyle}>
          <div>
            <div style={titleStyle}>Dashboard</div>
            <div style={subtitleStyle}>{new Date().toLocaleString()}</div>
          </div>
          <button type="button" style={runButtonStyle}>
            Run Reviewer Now
          </button>
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
      </div>
    </div>
  );
}
