import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";
import type { AgentId } from "../components/ChatMessage.js";

export type { AgentId };

export interface ChatMessage {
  id: number | string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
}

interface ChatState {
  activeAgent: AgentId;
  setActiveAgent: (agent: AgentId) => void;
  messagesByAgent: Record<AgentId, ChatMessage[]>;
  streamingByAgent: Record<AgentId, boolean>;
  streamingContentByAgent: Record<AgentId, string>;
  loadHistory: (agent: AgentId) => Promise<void>;
  sendMessage: (agent: AgentId, content: string) => Promise<void>;
  sendMessageStream: (agent: AgentId, content: string) => Promise<void>;
  appendStreamingDelta: (agent: AgentId, delta: string) => void;
  completeStreaming: (agent: AgentId, finalContent: string) => void;
}

let nextLocalId = 1;

// Initial state seeded with M4 Hall mock messages split by agentId, so
// dev-mode (non-Electron) rendering and existing jsdom tests continue to show
// meaningful data. When running inside Electron, loadHistory() overwrites these
// with live IPC data.
//
// Hall coordination model note: the plan originally used isolated per-agent
// threads. We keep the messagesByAgent shape for storage, but ChatPage flattens
// + sorts by timestamp for the shared Hall view and filters when an agent tab
// is selected.
const NOW = Date.now();

const INITIAL_MESSAGES: Record<AgentId, ChatMessage[]> = {
  analyzer: [
    {
      id: "m2",
      role: "assistant",
      content:
        "Scanning 142 active markets. Top momentum signals:\n\n- BTC > $100k by Apr 10 (net flow +$4.2k/min)\n- Lakers vs Celtics tonight (unique traders 7/min)\n- Trump approval > 50% by May (steady drift)",
      timestamp: NOW - 18 * 60_000,
    },
    {
      id: "m3",
      role: "user",
      content: "@analyzer what's driving the BTC market's acceleration right now?",
      timestamp: NOW - 15 * 60_000,
    },
    {
      id: "m4",
      role: "assistant",
      content:
        "Three concurrent factors:\n1. Spot BTC cleared $98.2k resistance 11 min ago\n2. Unique traders jumped from 3/min to 9/min\n3. YES side order book thickened 2.4x",
      timestamp: NOW - 14 * 60_000,
    },
  ],
  reviewer: [
    {
      id: "m5",
      role: "assistant",
      content:
        "Weekly review snapshot: bucket 0.40-0.45 remains the standout (71.4% win rate, +$56.20). Recommending we keep current sizing on that bucket and pull back on 0.55-0.60.",
      timestamp: NOW - 11 * 60_000,
    },
    {
      id: "m8",
      role: "user",
      content:
        "@reviewer should we push the filter proposal for min_unique_traders_1m tonight?",
      timestamp: NOW - 2 * 60_000,
    },
  ],
  risk_manager: [
    {
      id: "m1",
      role: "system",
      content:
        "Coordinator brief \u00B7 auto-generated 23 min ago\n\n7 triggers detected in past hour, 2 entered (BTC YES, Lakers NO). Net flow on US Election markets unusually elevated \u2014 consider tightening unique_traders_1m to 4.",
      timestamp: NOW - 23 * 60_000,
    },
    {
      id: "m6",
      role: "user",
      content:
        "@risk_manager are we close to any halts? What's our drawdown right now?",
      timestamp: NOW - 5 * 60_000,
    },
    {
      id: "m7",
      role: "assistant",
      content:
        "Currently safe on all halts:\n\n- Daily DD: -0.8% (halt at -2.0%)\n- Weekly DD: -1.5% (halt at -4.0%)\n- Total DD from peak: -1.2%\n\nRisk budget: $94.50 remaining today.",
      timestamp: NOW - 4 * 60_000,
    },
  ],
};

export const useChat = create<ChatState>((set, get) => ({
  activeAgent: "risk_manager",
  setActiveAgent: (agent) => {
    set({ activeAgent: agent });
    void get().loadHistory(agent);
  },
  messagesByAgent: INITIAL_MESSAGES,
  streamingByAgent: { analyzer: false, reviewer: false, risk_manager: false },
  streamingContentByAgent: { analyzer: "", reviewer: "", risk_manager: "" },

  loadHistory: async (agent) => {
    if (!isElectron()) return;
    const rows = await pmt.getChatHistory(agent, 50);
    const messages: ChatMessage[] = (
      rows as Array<{
        message_id: number;
        role: "user" | "assistant" | "system";
        content: string;
        created_at: number;
      }>
    )
      .map((r) => ({
        id: r.message_id,
        role: r.role,
        content: r.content,
        timestamp: r.created_at,
      }))
      .reverse(); // DB returns DESC, we display ASC
    set((state) => ({
      messagesByAgent: { ...state.messagesByAgent, [agent]: messages },
    }));
  },

  sendMessage: async (agent, content) => {
    // Optimistically append user message
    const userMsg: ChatMessage = {
      id: -nextLocalId++,
      role: "user",
      content,
      timestamp: Date.now(),
    };
    set((state) => ({
      messagesByAgent: {
        ...state.messagesByAgent,
        [agent]: [...state.messagesByAgent[agent], userMsg],
      },
    }));

    if (!isElectron()) return;
    try {
      const reply = await pmt.sendMessage(agent, content);
      const assistantMsg: ChatMessage = {
        id: -nextLocalId++,
        role: "assistant",
        content: reply.content,
        timestamp: Date.now(),
      };
      set((state) => ({
        messagesByAgent: {
          ...state.messagesByAgent,
          [agent]: [...state.messagesByAgent[agent], assistantMsg],
        },
      }));
    } catch (err) {
      const errMsg: ChatMessage = {
        id: -nextLocalId++,
        role: "assistant",
        content: `(Error: ${String(err)})`,
        timestamp: Date.now(),
      };
      set((state) => ({
        messagesByAgent: {
          ...state.messagesByAgent,
          [agent]: [...state.messagesByAgent[agent], errMsg],
        },
      }));
    }
  },

  sendMessageStream: async (agent, content) => {
    // Optimistically append user message
    const userMsg: ChatMessage = {
      id: -nextLocalId++,
      role: "user",
      content,
      timestamp: Date.now(),
    };
    set((state) => ({
      messagesByAgent: {
        ...state.messagesByAgent,
        [agent]: [...state.messagesByAgent[agent], userMsg],
      },
    }));

    if (!isElectron()) return;
    
    // Start streaming state
    set((state) => ({
      streamingByAgent: { ...state.streamingByAgent, [agent]: true },
      streamingContentByAgent: { ...state.streamingContentByAgent, [agent]: "" },
    }));

    try {
      // Initiate the stream - IPC will send events via on()
      await pmt.sendMessageStream(agent, content);
    } catch (err) {
      set((state) => ({
        streamingByAgent: { ...state.streamingByAgent, [agent]: false },
        messagesByAgent: {
          ...state.messagesByAgent,
          [agent]: [
            ...state.messagesByAgent[agent],
            {
              id: -nextLocalId++,
              role: "assistant",
              content: `(Error: ${String(err)})`,
              timestamp: Date.now(),
            },
          ],
        },
      }));
    }
  },

  appendStreamingDelta: (agent, delta) => {
    set((state) => ({
      streamingContentByAgent: {
        ...state.streamingContentByAgent,
        [agent]: state.streamingContentByAgent[agent] + delta,
      },
    }));
  },

  completeStreaming: (agent, finalContent) => {
    set((state) => ({
      streamingByAgent: { ...state.streamingByAgent, [agent]: false },
      streamingContentByAgent: { ...state.streamingContentByAgent, [agent]: "" },
      messagesByAgent: {
        ...state.messagesByAgent,
        [agent]: [
          ...state.messagesByAgent[agent],
          {
            id: -nextLocalId++,
            role: "assistant",
            content: finalContent,
            timestamp: Date.now(),
          },
        ],
      },
    }));
  },
}));
