import React from "react";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage.js";
import { SettingsPage } from "./pages/SettingsPage.js";
import { ReportsPage } from "./pages/ReportsPage.js";
import { ChatPage } from "./pages/ChatPage.js";

export function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
