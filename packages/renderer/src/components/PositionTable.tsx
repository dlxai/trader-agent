import React from "react";
import { theme } from "../theme.js";

export interface Position {
  signalId: string;
  marketTitle: string;
  side: "buy_yes" | "buy_no";
  entryPrice: number;
  currentPrice: number;
  sizeUsdc: number;
  pnl: number;
  heldDuration: string;
}

export interface PositionTableProps {
  positions: Position[];
}

const containerStyle: React.CSSProperties = {
  background: theme.colors.white,
  border: `1px solid ${theme.colors.borderGray}`,
  borderRadius: 12,
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  padding: "16px 20px",
  borderBottom: `1px solid ${theme.colors.borderGray}`,
  fontSize: 16,
  fontWeight: theme.font.weights.semibold,
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  fontSize: 13,
};

const thStyle: React.CSSProperties = {
  background: theme.colors.fafafa,
  color: theme.colors.coolGray,
  textTransform: "uppercase",
  fontSize: 11,
  textAlign: "left",
  padding: "12px 20px",
  fontWeight: theme.font.weights.medium,
};

const tdStyle: React.CSSProperties = {
  padding: "14px 20px",
  borderTop: `1px solid ${theme.colors.rowDivider}`,
};

function SideBadge({ side }: { side: "buy_yes" | "buy_no" }) {
  const isYes = side === "buy_yes";
  return (
    <span
      style={{
        background: isYes ? theme.colors.greenSubtle : "rgba(151,107,255,0.16)",
        color: isYes ? theme.colors.greenDark : theme.colors.purpleDeep,
        padding: "3px 8px",
        borderRadius: 6,
        fontSize: 11,
        fontWeight: theme.font.weights.medium,
      }}
    >
      {isYes ? "YES" : "NO"}
    </span>
  );
}

export function PositionTable({ positions }: PositionTableProps) {
  if (positions.length === 0) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>Open Positions</div>
        <div style={{ padding: "32px 20px", textAlign: "center", color: theme.colors.silverBlue }}>
          No open positions
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Open Positions</div>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Market</th>
            <th style={{ ...thStyle, padding: "12px" }}>Side</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>Entry</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>Now</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>Size</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>PnL</th>
            <th style={{ ...thStyle, textAlign: "right" }}>Held</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.signalId}>
              <td style={{ ...tdStyle, fontWeight: theme.font.weights.medium }}>
                {p.marketTitle}
              </td>
              <td style={{ ...tdStyle, padding: 14 }}>
                <SideBadge side={p.side} />
              </td>
              <td style={{ ...tdStyle, padding: 14, textAlign: "right" }}>{p.entryPrice.toFixed(3)}</td>
              <td style={{ ...tdStyle, padding: 14, textAlign: "right" }}>{p.currentPrice.toFixed(3)}</td>
              <td style={{ ...tdStyle, padding: 14, textAlign: "right" }}>${p.sizeUsdc.toFixed(0)}</td>
              <td
                style={{
                  ...tdStyle,
                  padding: 14,
                  textAlign: "right",
                  color: p.pnl >= 0 ? theme.colors.green : theme.colors.red,
                  fontWeight: theme.font.weights.medium,
                }}
              >
                {`${p.pnl >= 0 ? "+" : "-"}$${Math.abs(p.pnl).toFixed(2)}`}
              </td>
              <td style={{ ...tdStyle, textAlign: "right", color: theme.colors.coolGray }}>
                {p.heldDuration}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
