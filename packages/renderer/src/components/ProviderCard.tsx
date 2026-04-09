import React from "react";
import { theme } from "../theme.js";

export interface ProviderCardProps {
  name: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  authDetail?: string;
  models?: string[];
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export function ProviderCard({
  name,
  authType,
  isConnected,
  authDetail,
  models,
  onConnect,
  onDisconnect,
}: ProviderCardProps) {
  const borderColor = isConnected
    ? authType === "cli_credential" || authType === "oauth"
      ? theme.colors.green
      : theme.colors.purple
    : theme.colors.borderGray;
  const background = isConnected
    ? authType === "cli_credential" || authType === "oauth"
      ? theme.colors.greenBg
      : theme.colors.purpleBg
    : theme.colors.white;

  return (
    <div
      style={{
        border: `${isConnected ? 2 : 1}px solid ${borderColor}`,
        padding: 14,
        borderRadius: 10,
        background,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "start",
        }}
      >
        <div>
          <div
            style={{
              fontWeight: theme.font.weights.semibold,
              fontSize: 12,
            }}
          >
            {name}
          </div>
          <div
            style={{
              fontSize: 11,
              color: theme.colors.coolGray,
              marginTop: 2,
            }}
          >
            {authDetail ?? "Not configured"}
          </div>
        </div>
        {isConnected && (
          <div
            style={{
              fontSize: 11,
              color: theme.colors.green,
              fontWeight: theme.font.weights.medium,
            }}
          >
            {"\u25CF"} Connected
          </div>
        )}
      </div>
      {isConnected && models && models.length > 0 && (
        <div
          style={{
            fontSize: 11,
            color: theme.colors.silverBlue,
            marginTop: 8,
          }}
        >
          Models: {models.slice(0, 3).join(", ")}
          {models.length > 3 ? `, +${models.length - 3} more` : ""}
        </div>
      )}
      {!isConnected && onConnect && (
        <button
          type="button"
          onClick={onConnect}
          style={{
            background: theme.colors.purpleSubtle,
            color: theme.colors.purple,
            padding: "5px 12px",
            borderRadius: 6,
            fontSize: 11,
            marginTop: 8,
            fontWeight: theme.font.weights.medium,
            border: "none",
            cursor: "pointer",
          }}
        >
          + Add
          {authType === "oauth"
            ? " (OAuth)"
            : authType === "cli_credential"
              ? " (CLI)"
              : " key"}
        </button>
      )}
      {isConnected && onDisconnect && (
        <button
          type="button"
          onClick={onDisconnect}
          style={{
            background: "transparent",
            color: theme.colors.coolGray,
            padding: "5px 12px",
            borderRadius: 6,
            fontSize: 11,
            marginTop: 8,
            fontWeight: theme.font.weights.medium,
            border: `1px solid ${theme.colors.borderGray}`,
            cursor: "pointer",
          }}
        >
          Disconnect
        </button>
      )}
    </div>
  );
}
