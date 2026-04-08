/**
 * Electron preload script.
 *
 * Exposes a typed IPC surface on `window.pmt` via contextBridge. The renderer
 * imports the `PmtApi` type (ambient via the renderer's own augmentation) to
 * get full autocompletion without ever touching `ipcRenderer` directly.
 */
import { contextBridge, ipcRenderer } from "electron";

const api = {
  // Portfolio
  getPortfolioState: () => ipcRenderer.invoke("getPortfolioState"),
  getOpenPositions: () => ipcRenderer.invoke("getOpenPositions"),
  getRecentClosedTrades: (limit: number) =>
    ipcRenderer.invoke("getRecentClosedTrades", limit),

  // Coordinator
  getLatestCoordinatorBrief: () => ipcRenderer.invoke("getLatestCoordinatorBrief"),
  triggerCoordinatorNow: () => ipcRenderer.invoke("triggerCoordinatorNow"),

  // Reports
  getRecentReports: (limit: number) =>
    ipcRenderer.invoke("getRecentReports", limit),
  getReportContent: (reportPath: string) =>
    ipcRenderer.invoke("getReportContent", reportPath),
  triggerReviewerNow: () => ipcRenderer.invoke("triggerReviewerNow"),

  // Proposals
  getPendingProposals: () => ipcRenderer.invoke("getPendingProposals"),
  approveProposal: (id: number) => ipcRenderer.invoke("approveProposal", id),
  rejectProposal: (id: number) => ipcRenderer.invoke("rejectProposal", id),

  // Config
  getConfig: () => ipcRenderer.invoke("getConfig"),
  updateConfigField: (key: string, value: unknown) =>
    ipcRenderer.invoke("updateConfigField", key, value),

  // Providers
  listProviders: () => ipcRenderer.invoke("listProviders"),
  connectProvider: (providerId: string, credentials: unknown) =>
    ipcRenderer.invoke("connectProvider", providerId, credentials),
  disconnectProvider: (providerId: string) =>
    ipcRenderer.invoke("disconnectProvider", providerId),
  setAgentModel: (agentId: string, providerId: string, modelId: string) =>
    ipcRenderer.invoke("setAgentModel", agentId, providerId, modelId),

  // Chat
  getChatHistory: (agentId: string, limit: number) =>
    ipcRenderer.invoke("getChatHistory", agentId, limit),
  sendMessage: (agentId: string, content: string) =>
    ipcRenderer.invoke("sendMessage", agentId, content),
  clearChatHistory: (agentId: string) =>
    ipcRenderer.invoke("clearChatHistory", agentId),

  // Engine control
  pauseTrading: () => ipcRenderer.invoke("pauseTrading"),
  resumeTrading: () => ipcRenderer.invoke("resumeTrading"),
  emergencyStop: () => ipcRenderer.invoke("emergencyStop"),

  // Event subscriptions (Main -> Renderer push)
  on: (event: string, handler: (...args: unknown[]) => void) => {
    const wrapped = (_e: unknown, ...args: unknown[]) => handler(...args);
    ipcRenderer.on(event, wrapped);
    return () => ipcRenderer.removeListener(event, wrapped);
  },
};

contextBridge.exposeInMainWorld("pmt", api);

// Type augmentation for the renderer side
export type PmtApi = typeof api;
