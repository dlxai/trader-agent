import React from "react";
import { theme } from "../theme.js";

export interface EmployeeTabProps {
  icon: string;
  label: string;
  isActive: boolean;
  onClick: () => void;
}

export function EmployeeTab({ icon, label, isActive, onClick }: EmployeeTabProps) {
  return (
    <button
      type="button"
      aria-pressed={isActive}
      aria-label={label}
      onClick={onClick}
      style={{
        width: 44,
        height: 44,
        borderRadius: 12,
        background: isActive ? theme.colors.purple : "rgba(148,151,169,0.08)",
        boxShadow: isActive ? theme.shadow.whisper : undefined,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 22,
        color: isActive ? theme.colors.white : "inherit",
        cursor: "pointer",
        border: "none",
        padding: 0,
      }}
    >
      {icon}
    </button>
  );
}
