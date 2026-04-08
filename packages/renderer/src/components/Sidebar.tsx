import React from "react";
import { NavLink } from "react-router-dom";
import { theme } from "../theme.js";

const sidebarStyle: React.CSSProperties = {
  width: 220,
  background: theme.colors.fafafa,
  borderRight: `1px solid ${theme.colors.borderGray}`,
  padding: "24px 16px",
  flexShrink: 0,
  height: "100vh",
  overflowY: "auto",
};

const headerStyle: React.CSSProperties = {
  fontWeight: theme.font.weights.bold,
  fontSize: 20,
  letterSpacing: -0.5,
  marginBottom: 32,
  color: theme.colors.purple,
};

const sectionLabelStyle: React.CSSProperties = {
  fontSize: 12,
  textTransform: "uppercase",
  color: theme.colors.silverBlue,
  marginBottom: 12,
  fontWeight: theme.font.weights.medium,
};

interface NavItemProps {
  to: string;
  icon: string;
  label: string;
  badge?: number;
}

function NavItem({ to, icon, label, badge }: NavItemProps) {
  return (
    <NavLink
      to={to}
      style={({ isActive }) => ({
        display: "block",
        padding: "10px 12px",
        marginBottom: 4,
        borderRadius: 8,
        color: isActive ? theme.colors.purple : theme.colors.coolGray,
        background: isActive ? theme.colors.purpleSubtle : "transparent",
        fontWeight: isActive ? theme.font.weights.medium : theme.font.weights.regular,
        textDecoration: "none",
      })}
    >
      {icon} {label}
      {badge !== undefined && badge > 0 && (
        <span
          style={{
            background: theme.colors.red,
            color: theme.colors.white,
            borderRadius: 999,
            padding: "1px 6px",
            fontSize: 10,
            marginLeft: 6,
          }}
        >
          {badge}
        </span>
      )}
    </NavLink>
  );
}

interface EmployeeRowProps {
  icon: string;
  name: string;
  online: boolean;
}

function EmployeeRow({ icon, name, online }: EmployeeRowProps) {
  return (
    <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          width: 8,
          height: 8,
          background: online ? theme.colors.green : theme.colors.silverBlue,
          borderRadius: "50%",
          display: "inline-block",
        }}
      />
      {icon} {name}
    </div>
  );
}

export interface SidebarProps {
  pendingProposalCount: number;
}

export function Sidebar({ pendingProposalCount }: SidebarProps) {
  return (
    <nav style={sidebarStyle}>
      <div style={headerStyle}>Polymarket Trader</div>
      <div style={sectionLabelStyle}>Pages</div>
      <NavItem to="/" icon={"\u{1F4CA}"} label="Dashboard" />
      <NavItem to="/settings" icon={"\u2699\uFE0F"} label="Settings" badge={pendingProposalCount} />
      <NavItem to="/reports" icon={"\u{1F4C4}"} label="Reports" />
      <NavItem to="/chat" icon={"\u{1F4AC}"} label="Chat" />

      <div style={{ ...sectionLabelStyle, marginTop: 24 }}>Employees</div>
      <EmployeeRow icon={"\u{1F9E0}"} name="Analyzer" online={true} />
      <EmployeeRow icon={"\u{1F4CA}"} name="Reviewer" online={true} />
      <EmployeeRow icon={"\u{1F6E1}\uFE0F"} name="Risk Mgr" online={true} />
    </nav>
  );
}
