import React from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { KpiCard } from "../components/KpiCard.js";
import { PositionTable, type Position } from "../components/PositionTable.js";
import { CoordinatorBanner } from "../components/CoordinatorBanner.js";

// M4.6 — mock data only. M5 wires real IPC / stores.
const MOCK_PORTFOLIO = {
  equity: 10127.5,
  todayPnl: 127.5,
  weeklyWinRate: 0.625,
  weeklyWins: 15,
  weeklyTotal: 24,
  drawdownPct: -1.2,
  peakEquity: 10250,
  openPositionCount: 3,
  maxOpenPositions: 8,
  totalExposure: 342,
} as const;

const MOCK_POSITIONS: Position[] = [
  {
    signalId: "s1",
    marketTitle: "Trump approval > 50% by May",
    side: "buy_yes",
    entryPrice: 0.452,
    currentPrice: 0.481,
    sizeUsdc: 125,
    pnl: 8.02,
    heldDuration: "42m",
  },
  {
    signalId: "s2",
    marketTitle: "BTC > $100k by Apr 10",
    side: "buy_yes",
    entryPrice: 0.52,
    currentPrice: 0.508,
    sizeUsdc: 108,
    pnl: -2.49,
    heldDuration: "1h 18m",
  },
  {
    signalId: "s3",
    marketTitle: "Lakers vs Celtics tonight",
    side: "buy_no",
    entryPrice: 0.38,
    currentPrice: 0.395,
    sizeUsdc: 109,
    pnl: 3.81,
    heldDuration: "2h 04m",
  },
];

const MOCK_COORDINATOR = {
  latestSummary:
    "7 triggers detected in last hour, 2 entered. PnL +$8.34. Net flow on US Election markets unusually elevated \u2014 consider tightening unique_traders_1m to 4.",
  generatedMinutesAgo: 23,
} as const;

const MOCK_PENDING_PROPOSAL_COUNT = 0;

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
  fontSize: 14,
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
  const portfolio = MOCK_PORTFOLIO;
  const positions = MOCK_POSITIONS;
  const coordinator = MOCK_COORDINATOR;

  const todayPnlPrefix = portfolio.todayPnl >= 0 ? "+" : "-";
  const todayPnlText = `${todayPnlPrefix}$${Math.abs(portfolio.todayPnl).toFixed(2)} today`;

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={MOCK_PENDING_PROPOSAL_COUNT} />
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
