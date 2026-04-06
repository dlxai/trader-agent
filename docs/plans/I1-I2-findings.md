# Investigation I1 + I2 — OpenClaw Plugin → Agent Integration

**Date:** 2026-04-06
**Investigator:** Claude Code Explore subagent
**Source consulted:** D:/work/dlxiaclaw/vendor/openclaw/ (read-only reference)

---

## I1: Plugin → Agent Invocation

### Verdict: **FEASIBLE** (via Gateway RPC)

### Findings

OpenClaw does not expose a direct plugin-to-agent invocation API. Instead, plugins communicate with the Gateway via the GatewayClient (WebSocket RPC).

**Key files:**
- `D:/work/dlxiaclaw/vendor/openclaw/src/gateway/client.ts:814` — GatewayClient.request
- `D:/work/dlxiaclaw/vendor/openclaw/src/gateway/server-cron.ts:144` — buildGatewayCronService
- `D:/work/dlxiaclaw/extensions/rivonclaw-event-bridge/src/index.ts:76` — api.registerGatewayMethod example

### Recommended approach

Use the cron API with polling:

1. During plugin setup, create a persistent cron job that runs polymarket-analyzer
2. When Collector detects a signal, call gateway.request("cron.run", { jobId, mode: "force" })
3. Poll gateway.request("cron.runs", { jobId, limit: 1 }) to get results
4. Extract outputText from the run log for the verdict

### Code template

```typescript
export async function setupPolymarketCollector(api: PluginApi) {
  try {
    const job = await api.gateway.request("cron.add", {
      name: "polymarket-signal-collector",
      schedule: { kind: "every", everyMs: 300_000 },
      sessionTarget: "isolated",
      payload: {
        kind: "agentTurn",
        message: "Check for Polymarket signals and generate verdict.",
      },
      delivery: { mode: "none" },
      agentId: "polymarket-analyzer",
      enabled: true,
    });
    jobId = job.id;
  } catch (err) {
    api.logger.warn(`Cron job exists: ${err}`);
  }

  async function judgeSignal(signal: PolymarketSignal): Promise<string> {
    await api.gateway.request("cron.run", { jobId, mode: "force" });
    
    const maxRetries = 10;
    for (let i = 0; i < maxRetries; i++) {
      await new Promise(r => setTimeout(r, 500));
      const runs = await api.gateway.request("cron.runs", { jobId, limit: 1 });
      const latestRun = runs.entries?.[0];
      if (latestRun?.status === "ok") {
        return latestRun.summary || latestRun.data?.outputText || "ok";
      }
      if (latestRun?.status === "error") {
        throw new Error(`Cron run failed: ${latestRun.error}`);
      }
    }
    throw new Error("Cron did not complete in time");
  }

  return { judgeSignal };
}
```

### Open issues / unknowns

1. Does chat.run() exist as a faster alternative?
2. Can agentId explicitly select the analyzer agent?
3. Exact return type of cron.runs?
4. Does agent know it was triggered by cron?

---

## I2: OpenClaw Cron

### Verdict: **FEASIBLE** (fully documented)

### Findings

OpenClaw has a mature cron system with persistence, scheduling, and delivery modes.

**Key files:**
- `D:/work/dlxiaclaw/vendor/openclaw/src/cron/types.ts` — TypeScript types
- `D:/work/dlxiaclaw/vendor/openclaw/src/gateway/protocol/schema/cron.ts` — Zod validation
- `D:/work/dlxiaclaw/vendor/openclaw/src/gateway/server-methods/cron.ts:44-309` — RPC methods
- `D:/work/dlxiaclaw/vendor/openclaw/docs/automation/cron-jobs.md` — User docs

**Storage:** `~/.openclaw/cron/jobs.json` by default

**Schedule schema:**
- `{ kind: "at"; at: string }` — ISO 8601, one-shot
- `{ kind: "every"; everyMs: number }` — fixed interval
- `{ kind: "cron"; expr: string; tz?: string }` — cron expression with optional timezone

**Payload schema:**
- `{ kind: "systemEvent"; text: string }` — main session event
- `{ kind: "agentTurn"; message: string }` — isolated agent turn

### Configuration template

**For polymarket-reviewer at 00:00 UTC:**

Via CLI (Recommended):

```bash
openclaw cron add \
  --name "Polymarket Daily Reviewer" \
  --cron "0 0 * * *" \
  --tz "UTC" \
  --session isolated \
  --message "Review all Polymarket positions from past 24 hours." \
  --announce \
  --channel slack \
  --to "channel:C1234567890" \
  --agent polymarket-reviewer
```

Via Gateway RPC:

```typescript
const job = await gateway.request("cron.add", {
  name: "Polymarket Daily Reviewer",
  agentId: "polymarket-reviewer",
  schedule: {
    kind: "cron",
    expr: "0 0 * * *",
    tz: "UTC",
  },
  sessionTarget: "isolated",
  wakeMode: "next-heartbeat",
  payload: {
    kind: "agentTurn",
    message: "Review all Polymarket positions from past 24 hours.",
  },
  delivery: {
    mode: "announce",
    channel: "slack",
    to: "channel:C1234567890",
  },
  enabled: true,
});
```

### How the agent receives the trigger

When a cron job with `payload.kind = "agentTurn"` executes:

1. Cron service enqueues a cron session
2. Isolated agent runner executes the agent with the message
3. Agent sees no special trigger marker — looks like normal user message

### Open issues / unknowns

1. Is wakeMode: "force" supported?
2. How does stagger apply to "0 0 * * *"?
3. Does agent have cron metadata access?
4. Can user update via cron.update? Yes, documented in server-methods.

---

## Cross-cutting concerns

1. **Session management:** Cron jobs use separate sessions. Persist state to memory/workspace.
2. **Model selection:** Cron payload supports model and fallbacks overrides.
3. **Delivery failures:** Poll cron.runs to detect and handle failures.
4. **Agent IDs:** Always explicitly specify agent IDs.
5. **Timezone:** Always use explicit tz to avoid host timezone surprises.

---

## Next steps

No changes to polymarket-trader plan required. Both questions answered.

### I1 Action Items:
1. Implement Collector with cron job creation and polling
2. Verify if chat.run() exists

### I2 Action Items:
1. Create polymarket-reviewer cron job (manual user step)
2. Document timezone requirement in README

Architecture is sound. Implementation can proceed.
