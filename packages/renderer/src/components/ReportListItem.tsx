import React from "react";
import { theme } from "../theme.js";

export interface ReportListItemProps {
  date: string;
  period: "daily" | "weekly";
  tradeCount: number;
  netPnl: number;
  isSelected: boolean;
  onClick: () => void;
}

export function ReportListItem({
  date,
  period,
  tradeCount,
  netPnl,
  isSelected,
  onClick,
}: ReportListItemProps) {
  const pnlColor = netPnl >= 0 ? theme.colors.green : theme.colors.red;
  const pnlPrefix = netPnl >= 0 ? "+" : "-";
  const pnlText = `${pnlPrefix}$${Math.abs(netPnl).toFixed(2)}`;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{
        background: isSelected ? theme.colors.purpleSubtle : "transparent",
        color: isSelected ? theme.colors.purple : "inherit",
        padding: "12px 14px",
        borderRadius: 8,
        marginBottom: 4,
        cursor: "pointer",
      }}
    >
      <div
        style={{
          fontWeight: isSelected
            ? theme.font.weights.semibold
            : theme.font.weights.medium,
          fontSize: 13,
        }}
      >
        {date}
      </div>
      <div
        style={{
          fontSize: 11,
          marginTop: 2,
          color: isSelected ? theme.colors.purple : pnlColor,
        }}
      >
        {period === "weekly" ? "Weekly" : "Daily"} · {tradeCount} trades ·{" "}
        {pnlText}
      </div>
    </div>
  );
}
