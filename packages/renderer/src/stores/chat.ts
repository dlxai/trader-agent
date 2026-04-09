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

// No mock data - only real data from backend via IPC
const INITIAL_MESSAGES: Record<AgentId, ChatMessage[]> = {
  analyzer: [],
  reviewer: [],
  risk_manager: [],
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
