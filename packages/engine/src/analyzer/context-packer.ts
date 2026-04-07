import type { TriggerEvent } from "../bus/types.js";

function formatDuration(ms: number): string {
  const sec = Math.floor(ms / 1000);
  if (sec < 3600) return `${Math.floor(sec / 60)} minutes`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${h}h ${m}m`;
}

export function packContext(trigger: TriggerEvent): string {
  const resolveIn = formatDuration(trigger.resolves_at - trigger.triggered_at);
  return `You are judging a Polymarket trading signal.

Market: "${trigger.market_title}"
Market ID: ${trigger.market_id}
Current price: ${trigger.snapshot.current_mid_price.toFixed(4)}
Resolves in: ${resolveIn}
Liquidity: $${trigger.snapshot.liquidity.toFixed(0)}

Detected flow indicators:
- Volume (1m): $${trigger.snapshot.volume_1m.toFixed(0)}
- Net flow (1m): $${trigger.snapshot.net_flow_1m.toFixed(0)} (${trigger.direction === "buy_yes" ? "toward YES" : "toward NO"})
- Unique traders (1m): ${trigger.snapshot.unique_traders_1m}
- Price move (5m): ${(trigger.snapshot.price_move_5m * 100).toFixed(2)}%

Suggested direction from flow: ${trigger.direction}

Your task: assess whether this is a real actionable signal or noise (bots, manipulation, illiquid, irrelevant).

Respond with ONLY a JSON object in this exact schema (no extra commentary):

{
  "verdict": "real_signal" | "noise" | "uncertain",
  "direction": "buy_yes" | "buy_no",
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation"
}

Use "real_signal" only when you are confident. Use "uncertain" when ambiguous. Use "noise" when you see red flags (bot patterns, low liquidity, micro-market irrelevance).`;
}
