// scripts/record-ws.mjs
// Usage: node scripts/record-ws.mjs > tests/fixtures/polymarket-ws-sample.json
// Records 1 hour of Polymarket trade events to stdout as JSON.
import WebSocket from "ws";

const URL = process.env.POLYMARKET_WS_URL ?? "wss://ws-subscriptions-clob.polymarket.com/ws/";
const DURATION_MS = 60 * 60 * 1000;

const ws = new WebSocket(URL);
const events = [];
const startMs = Date.now();

ws.on("open", () => {
  ws.send(JSON.stringify({ type: "SUBSCRIBE", channel: "market" }));
  console.error(`Recording for ${DURATION_MS / 1000}s...`);
});
ws.on("message", (data) => {
  try {
    const parsed = JSON.parse(data.toString());
    if (parsed.event_type === "trade") {
      events.push(parsed);
    }
  } catch {
    // ignore non-JSON / non-trade messages
  }
  if (Date.now() - startMs > DURATION_MS) {
    console.log(JSON.stringify(events));
    process.exit(0);
  }
});
ws.on("error", (err) => {
  console.error(`WS error: ${err.message}`);
  process.exit(1);
});
