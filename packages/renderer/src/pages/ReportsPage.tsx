import React, { useState } from "react";
import { theme } from "../theme.js";
import { Sidebar } from "../components/Sidebar.js";
import { ReportListItem } from "../components/ReportListItem.js";
import { BucketTable, type BucketRow } from "../components/BucketTable.js";

// M4.14 — mock data only. M5 wires real IPC / stores.

interface MockProposal {
  kind: "auto" | "pending";
  field: string;
  change: string;
}

interface MockReport {
  id: string;
  date: string;
  period: "daily" | "weekly";
  tradeCount: number;
  netPnl: number;
  totalPnl7d: number;
  winRate: number;
  weeklyWins: number;
  weeklyTotal: number;
  sharpe: number;
  buckets: BucketRow[];
  notes: string;
  proposals: MockProposal[];
}

const MOCK_REPORTS: MockReport[] = [
  {
    id: "2026-04-06",
    date: "Apr 6, 2026",
    period: "weekly",
    tradeCount: 24,
    netPnl: 127.5,
    totalPnl7d: 127.5,
    winRate: 0.625,
    weeklyWins: 15,
    weeklyTotal: 24,
    sharpe: 1.42,
    buckets: [
      { bucket: 0.3, trades: 3, wins: 2, winRate: 0.667, netPnl: 24.1 },
      { bucket: 0.4, trades: 7, wins: 5, winRate: 0.714, netPnl: 56.2 },
      { bucket: 0.45, trades: 9, wins: 5, winRate: 0.556, netPnl: 31.4 },
      { bucket: 0.5, trades: 4, wins: 2, winRate: 0.5, netPnl: 15.8 },
      { bucket: 0.85, trades: 1, wins: 1, winRate: 1.0, netPnl: 0 },
    ],
    notes:
      "Strong week. Bucket 0.40-0.45 was the standout performer (71% win rate). One concerning pattern: 4 of 9 losses hit the time-stop instead of stop loss.",
    proposals: [
      { kind: "auto", field: "min_net_flow_1m", change: "3000 \u2192 3500" },
      {
        kind: "pending",
        field: "min_unique_traders_1m",
        change: "3 \u2192 4",
      },
      {
        kind: "pending",
        field: "take_profit_pct",
        change: "0.10 \u2192 0.08",
      },
    ],
  },
  {
    id: "2026-04-05",
    date: "Apr 5, 2026",
    period: "daily",
    tradeCount: 4,
    netPnl: 18.2,
    totalPnl7d: 0,
    winRate: 0,
    weeklyWins: 0,
    weeklyTotal: 0,
    sharpe: 0,
    buckets: [],
    notes: "",
    proposals: [],
  },
  {
    id: "2026-04-04",
    date: "Apr 4, 2026",
    period: "daily",
    tradeCount: 3,
    netPnl: -8.4,
    totalPnl7d: 0,
    winRate: 0,
    weeklyWins: 0,
    weeklyTotal: 0,
    sharpe: 0,
    buckets: [],
    notes: "",
    proposals: [],
  },
];

const MOCK_PENDING_PROPOSAL_COUNT = 2;

const layoutStyle: React.CSSProperties = {
  display: "flex",
  minHeight: "100vh",
  background: theme.colors.fafafa,
};

const mainStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  maxHeight: "100vh",
  overflow: "hidden",
};

const innerSplitStyle: React.CSSProperties = {
  display: "flex",
  flex: 1,
  overflow: "hidden",
};

const listColumnStyle: React.CSSProperties = {
  width: 280,
  borderRight: `1px solid ${theme.colors.borderGray}`,
  padding: "20px 0",
  overflowY: "auto",
  flexShrink: 0,
  background: theme.colors.white,
};

const detailColumnStyle: React.CSSProperties = {
  flex: 1,
  padding: 32,
  overflowY: "auto",
};

export function ReportsPage() {
  const firstReport = MOCK_REPORTS[0];
  const initialId = firstReport ? firstReport.id : "";
  const [selectedId, setSelectedId] = useState<string>(initialId);
  const selected =
    MOCK_REPORTS.find((r) => r.id === selectedId) ?? firstReport;

  return (
    <div style={layoutStyle}>
      <Sidebar pendingProposalCount={MOCK_PENDING_PROPOSAL_COUNT} />
      <div style={mainStyle}>
        <div style={innerSplitStyle}>
          {/* Report list */}
          <div style={listColumnStyle}>
            <div style={{ padding: "0 20px 16px" }}>
              <div
                style={{
                  fontSize: 24,
                  fontWeight: theme.font.weights.bold,
                  letterSpacing: -0.5,
                }}
              >
                Reports
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: theme.colors.silverBlue,
                  marginTop: 4,
                }}
              >
                Reviewer history
              </div>
            </div>
            <div style={{ padding: "0 20px" }}>
              {MOCK_REPORTS.map((r) => (
                <ReportListItem
                  key={r.id}
                  date={r.date}
                  period={r.period}
                  tradeCount={r.tradeCount}
                  netPnl={r.netPnl}
                  isSelected={r.id === selectedId}
                  onClick={() => setSelectedId(r.id)}
                />
              ))}
            </div>
          </div>

          {/* Report content */}
          <div style={detailColumnStyle}>
            {selected ? (
              <ReportDetail report={selected} />
            ) : (
              <div style={{ color: theme.colors.silverBlue }}>
                No report selected.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface ReportDetailProps {
  report: MockReport;
}

function ReportDetail({ report }: ReportDetailProps) {
  const pnl7dPrefix = report.totalPnl7d >= 0 ? "+" : "-";
  const pnl7dText = `${pnl7dPrefix}$${Math.abs(report.totalPnl7d).toFixed(2)}`;
  return (
    <>
      <div
        style={{
          fontSize: 24,
          fontWeight: theme.font.weights.bold,
          letterSpacing: -0.5,
        }}
      >
        {report.period === "weekly" ? "Weekly Review" : "Daily Review"} ·{" "}
        {report.date}
      </div>
      <div
        style={{
          fontSize: 13,
          color: theme.colors.silverBlue,
          marginTop: 4,
          marginBottom: 24,
        }}
      >
        Generated by Reviewer · claude-sonnet-4-6
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
          marginBottom: 24,
        }}
      >
        <div
          style={{
            background: theme.colors.greenBg,
            border: `1px solid rgba(20,158,97,0.2)`,
            padding: 14,
            borderRadius: 10,
          }}
        >
          <div
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              color: theme.colors.coolGray,
              fontWeight: theme.font.weights.medium,
            }}
          >
            7d Net PnL
          </div>
          <div
            style={{
              fontSize: 20,
              fontWeight: theme.font.weights.bold,
              color:
                report.totalPnl7d >= 0
                  ? theme.colors.green
                  : theme.colors.red,
              marginTop: 4,
            }}
          >
            {pnl7dText}
          </div>
        </div>
        <div
          style={{
            background: theme.colors.white,
            border: `1px solid ${theme.colors.borderGray}`,
            padding: 14,
            borderRadius: 10,
          }}
        >
          <div
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              color: theme.colors.coolGray,
              fontWeight: theme.font.weights.medium,
            }}
          >
            Win rate
          </div>
          <div
            style={{
              fontSize: 20,
              fontWeight: theme.font.weights.bold,
              marginTop: 4,
            }}
          >
            {(report.winRate * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: 11, color: theme.colors.coolGray }}>
            {report.weeklyWins} / {report.weeklyTotal} trades
          </div>
        </div>
        <div
          style={{
            background: theme.colors.white,
            border: `1px solid ${theme.colors.borderGray}`,
            padding: 14,
            borderRadius: 10,
          }}
        >
          <div
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              color: theme.colors.coolGray,
              fontWeight: theme.font.weights.medium,
            }}
          >
            Sharpe
          </div>
          <div
            style={{
              fontSize: 20,
              fontWeight: theme.font.weights.bold,
              marginTop: 4,
            }}
          >
            {report.sharpe.toFixed(2)}
          </div>
        </div>
      </div>

      <h3
        style={{
          fontSize: 18,
          fontWeight: theme.font.weights.semibold,
          margin: "24px 0 12px",
        }}
      >
        Per-bucket performance
      </h3>
      <BucketTable rows={report.buckets} />

      <h3
        style={{
          fontSize: 18,
          fontWeight: theme.font.weights.semibold,
          margin: "24px 0 12px",
        }}
      >
        Notes from Reviewer
      </h3>
      <div
        style={{
          background: theme.colors.fafafa,
          padding: 16,
          borderRadius: 8,
          fontSize: 13,
          lineHeight: 1.6,
        }}
      >
        {report.notes || "(no notes)"}
      </div>

      <h3
        style={{
          fontSize: 18,
          fontWeight: theme.font.weights.semibold,
          margin: "24px 0 12px",
        }}
      >
        Filter proposals
      </h3>
      {report.proposals.length === 0 ? (
        <div
          style={{
            fontSize: 13,
            color: theme.colors.silverBlue,
          }}
        >
          No filter proposals for this report.
        </div>
      ) : (
        <ul style={{ fontSize: 13, paddingLeft: 20 }}>
          {report.proposals.map((p) => (
            <li key={`${p.field}-${p.kind}`} style={{ marginBottom: 4 }}>
              <strong>
                {p.kind === "auto" ? "Auto-applied" : "Pending review"}
              </strong>
              : <code>{p.field}</code> {p.change}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
