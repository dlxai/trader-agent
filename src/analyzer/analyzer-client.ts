import { parseVerdict } from "./verdict-parser.js";
import type { ParsedVerdict } from "./verdict-parser.js";
import { LlmTimeoutError } from "../util/errors.js";

/**
 * Abstracts the mechanism for invoking an OpenClaw agent. The concrete
 * implementation in src/index.ts will use OpenClaw's gateway cron API
 * (cron.run + cron.runs polling) per the I1 investigation findings —
 * see docs/plans/I1-I2-findings.md for details.
 */
export type AgentInvoker = (agentId: string, message: string) => Promise<string>;

export interface AnalyzerClientOptions {
  agentId: string;
  timeoutMs: number;
  invoker: AgentInvoker;
}

export interface AnalyzerClient {
  judge(prompt: string): Promise<ParsedVerdict>;
}

export function createAnalyzerClient(opts: AnalyzerClientOptions): AnalyzerClient {
  return {
    async judge(prompt: string): Promise<ParsedVerdict> {
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new LlmTimeoutError(opts.timeoutMs)), opts.timeoutMs)
      );
      const raw = await Promise.race([opts.invoker(opts.agentId, prompt), timeoutPromise]);
      return parseVerdict(raw);
    },
  };
}
