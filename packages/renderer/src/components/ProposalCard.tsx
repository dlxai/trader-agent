import React from "react";
import { theme } from "../theme.js";

export interface ProposalCardProps {
  field: string;
  oldValue: string;
  proposedValue: string;
  rationale: string;
  onApprove: () => void;
  onReject: () => void;
}

export function ProposalCard({
  field,
  oldValue,
  proposedValue,
  rationale,
  onApprove,
  onReject,
}: ProposalCardProps) {
  return (
    <div
      style={{
        border: `1px solid ${theme.colors.borderGray}`,
        borderRadius: 10,
        padding: 16,
        marginBottom: 12,
      }}
    >
      <div style={{ fontWeight: theme.font.weights.medium }}>
        {field}:{" "}
        <span
          style={{
            textDecoration: "line-through",
            color: theme.colors.silverBlue,
          }}
        >
          {oldValue}
        </span>
        {" \u2192 "}
        <strong>{proposedValue}</strong>
      </div>
      <div
        style={{
          fontSize: 12,
          color: theme.colors.coolGray,
          margin: "6px 0",
        }}
      >
        {rationale}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button
          type="button"
          onClick={onApprove}
          style={{
            background: theme.colors.purple,
            color: theme.colors.white,
            padding: "8px 14px",
            borderRadius: 8,
            fontSize: 12,
            fontWeight: theme.font.weights.medium,
            border: "none",
            cursor: "pointer",
          }}
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onReject}
          style={{
            background: "rgba(148,151,169,0.08)",
            color: theme.colors.nearBlack,
            padding: "8px 14px",
            borderRadius: 8,
            fontSize: 12,
            fontWeight: theme.font.weights.medium,
            border: "none",
            cursor: "pointer",
          }}
        >
          Reject
        </button>
      </div>
    </div>
  );
}
