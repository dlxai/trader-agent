import React from "react";
import { theme } from "../theme.js";

export interface CoordinatorBannerProps {
  summary: string;
  generatedMinutesAgo: number;
}

export function CoordinatorBanner({ summary, generatedMinutesAgo }: CoordinatorBannerProps) {
  return (
    <div
      style={{
        background: theme.colors.purpleBg,
        borderLeft: `3px solid ${theme.colors.purple}`,
        padding: "16px 20px",
        borderRadius: 8,
        marginBottom: 24,
      }}
    >
      <div
        style={{
          fontSize: 12,
          textTransform: "uppercase",
          color: theme.colors.purpleDark,
          fontWeight: theme.font.weights.bold,
          marginBottom: 6,
        }}
      >
        {"\u{1F6E1}\uFE0F"} Coordinator Brief — {generatedMinutesAgo}m ago
      </div>
      <div
        style={{
          fontSize: 14,
          color: theme.colors.nearBlack,
          lineHeight: 1.5,
        }}
      >
        {summary}
      </div>
    </div>
  );
}
