import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockIpcMain } = vi.hoisted(() => ({
  mockIpcMain: {
    handle: vi.fn(),
    on: vi.fn(),
  },
}));

vi.mock("electron", () => ({
  ipcMain: mockIpcMain,
}));

import { registerIpcHandlers } from "../src/ipc.js";

describe("registerIpcHandlers", () => {
  beforeEach(() => {
    mockIpcMain.handle.mockClear();
  });

  it("registers all expected request/response handlers", () => {
    registerIpcHandlers({
      getEngineContext: () => null,
      getRiskMgrRunner: () => null,
      getReviewerScheduler: () => null,
      getCoordinatorScheduler: () => null,
      getMainWindow: () => null,
    });
    const registered = mockIpcMain.handle.mock.calls.map((c) => c[0]);
    expect(registered).toContain("getPortfolioState");
    expect(registered).toContain("getOpenPositions");
    expect(registered).toContain("getRecentClosedTrades");
    expect(registered).toContain("getLatestCoordinatorBrief");
    expect(registered).toContain("getRecentReports");
    expect(registered).toContain("getPendingProposals");
    expect(registered).toContain("approveProposal");
    expect(registered).toContain("rejectProposal");
    expect(registered).toContain("getConfig");
    expect(registered).toContain("updateConfigField");
    expect(registered).toContain("listProviders");
    expect(registered).toContain("connectProvider");
    expect(registered).toContain("disconnectProvider");
    expect(registered).toContain("setAgentModel");
    expect(registered).toContain("getChatHistory");
    expect(registered).toContain("sendMessage");
    expect(registered).toContain("clearChatHistory");
    expect(registered).toContain("pauseTrading");
    expect(registered).toContain("resumeTrading");
    expect(registered).toContain("emergencyStop");
    expect(registered).toContain("triggerReviewerNow");
    expect(registered).toContain("triggerCoordinatorNow");
  });
});
