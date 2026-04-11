import React, { useEffect } from "react";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { DashboardPage } from "./pages/DashboardPage.js";
import { SettingsPage } from "./pages/SettingsPage.js";
import { ReportsPage } from "./pages/ReportsPage.js";
import { ChatPage } from "./pages/ChatPage.js";
import { pmt, isElectron } from "./ipc-client.js";
import { useChat } from "./stores/chat.js";
import { useCoordinator, type Alert } from "./stores/coordinator.js";

// Setup IPC event listeners for streaming chat and other push events
function useIpcListeners() {
  useEffect(() => {
    if (!isElectron()) return;

    const { appendStreamingDelta, completeStreaming } = useChat.getState();
    const { setLatestBrief } = useCoordinator.getState();

    // Listen for streaming chat events from main process
    const unsubStart = pmt.on("chat:streaming:start", (payload: unknown) => {
      const { agentId } = payload as { agentId: string };
      // Streaming started - UI already shows loading state via streamingByAgent
      console.log("[IPC] Streaming started for", agentId);
    });

    const unsubDelta = pmt.on("chat:streaming:delta", (payload: unknown) => {
      const { agentId, delta } = payload as { agentId: string; delta: string };
      appendStreamingDelta(agentId as "analyzer" | "reviewer" | "risk_manager", delta);
    });

    const unsubComplete = pmt.on("chat:streaming:complete", (payload: unknown) => {
      const { agentId, content } = payload as { agentId: string; content: string };
      completeStreaming(agentId as "analyzer" | "reviewer" | "risk_manager", content);
    });

    const unsubMessage = pmt.on("chat:message", (payload: unknown) => {
      // New message added (e.g., user message from another source)
      const { agentId, role, content } = payload as { agentId: string; role: string; content: string };
      console.log("[IPC] New message for", agentId, role);
      // Refresh history to get the latest
      useChat.getState().loadHistory(agentId as "analyzer" | "reviewer" | "risk_manager");
    });

    // Listen for Coordinator brief updates
    const unsubBrief = pmt.on("coordinator:brief", (payload: unknown) => {
      const brief = payload as { summary: string; alerts: Alert[]; suggestions: string[] };
      console.log("[IPC] Coordinator brief received");
      setLatestBrief(brief);
    });

    return () => {
      unsubStart();
      unsubDelta();
      unsubComplete();
      unsubMessage();
      unsubBrief();
    };
  }, []);
}

function AppContent() {
  useIpcListeners();
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/reports" element={<ReportsPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <HashRouter>
      <AppContent />
    </HashRouter>
  );
}
