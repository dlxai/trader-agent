import React from "react";
import { theme } from "../theme.js";

export interface BucketRow {
  bucket: number;
  trades: number;
  wins: number;
  winRate: number;
  netPnl: number;
}

export interface BucketTableProps {
  rows: BucketRow[];
}

const headerCellBase: React.CSSProperties = {
  padding: 10,
};

export function BucketTable({ rows }: BucketTableProps) {
  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <thead>
        <tr
          style={{
            background: theme.colors.fafafa,
            fontSize: 11,
            textTransform: "uppercase",
            color: theme.colors.coolGray,
          }}
        >
          <th style={{ ...headerCellBase, textAlign: "left" }}>Bucket</th>
          <th style={{ ...headerCellBase, textAlign: "right" }}>Trades</th>
          <th style={{ ...headerCellBase, textAlign: "right" }}>Wins</th>
          <th style={{ ...headerCellBase, textAlign: "right" }}>Win rate</th>
          <th style={{ ...headerCellBase, textAlign: "right" }}>Net PnL</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td
              colSpan={5}
              style={{
                padding: 16,
                textAlign: "center",
                color: theme.colors.silverBlue,
                fontSize: 12,
              }}
            >
              No bucket data for this report.
            </td>
          </tr>
        ) : (
          rows.map((r) => {
            const pnlPrefix = r.netPnl >= 0 ? "+" : "-";
            const pnlText = `${pnlPrefix}$${Math.abs(r.netPnl).toFixed(2)}`;
            return (
              <tr
                key={r.bucket}
                style={{
                  borderBottom: `1px solid ${theme.colors.rowDivider}`,
                }}
              >
                <td style={{ padding: 10 }}>{r.bucket.toFixed(2)}</td>
                <td style={{ padding: 10, textAlign: "right" }}>{r.trades}</td>
                <td style={{ padding: 10, textAlign: "right" }}>{r.wins}</td>
                <td style={{ padding: 10, textAlign: "right" }}>
                  {(r.winRate * 100).toFixed(1)}%
                </td>
                <td
                  style={{
                    padding: 10,
                    textAlign: "right",
                    color:
                      r.netPnl >= 0 ? theme.colors.green : theme.colors.red,
                  }}
                >
                  {pnlText}
                </td>
              </tr>
            );
          })
        )}
      </tbody>
    </table>
  );
}
