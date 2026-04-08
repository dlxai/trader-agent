import React from "react";
import { theme } from "../theme.js";

export interface KpiCardProps {
  label: string;
  value: string;
  subtitle?: string;
  subtitleColor?: "green" | "red" | "neutral";
}

const cardStyle: React.CSSProperties = {
  background: theme.colors.white,
  border: `1px solid ${theme.colors.borderGray}`,
  padding: 16,
  borderRadius: 12,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: theme.colors.silverBlue,
  textTransform: "uppercase",
  fontWeight: theme.font.weights.medium,
};

const valueStyle: React.CSSProperties = {
  fontSize: 24,
  fontWeight: theme.font.weights.bold,
  marginTop: 4,
};

export function KpiCard({ label, value, subtitle, subtitleColor }: KpiCardProps) {
  const color =
    subtitleColor === "green"
      ? theme.colors.green
      : subtitleColor === "red"
      ? theme.colors.red
      : theme.colors.coolGray;
  return (
    <div style={cardStyle}>
      <div style={labelStyle}>{label}</div>
      <div style={valueStyle}>{value}</div>
      {subtitle && (
        <div style={{ fontSize: 12, color, marginTop: 2 }}>{subtitle}</div>
      )}
    </div>
  );
}
