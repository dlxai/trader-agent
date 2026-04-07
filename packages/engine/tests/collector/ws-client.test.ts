import { describe, it, expect, afterEach } from "vitest";
import { WebSocketServer } from "ws";
import { createPolymarketWsClient } from "../../src/collector/ws-client.js";

describe("polymarketWsClient", () => {
  let server: WebSocketServer | null = null;

  afterEach(() => {
    server?.close();
    server = null;
  });

  it("connects, receives a message, and forwards parsed trade events", async () => {
    server = new WebSocketServer({ port: 18761 });
    server.on("connection", (socket) => {
      socket.send(
        JSON.stringify({
          event_type: "trade",
          market: "m1",
          asset_id: "token-yes",
          price: "0.55",
          side: "BUY",
          size: "250.0",
          taker: "0xabc",
          timestamp: "1700000000000",
        })
      );
    });

    const received: unknown[] = [];
    const client = createPolymarketWsClient({
      url: "ws://127.0.0.1:18761",
      onTrade: (t) => received.push(t),
      onError: () => {},
    });
    await client.connect();
    await new Promise((r) => setTimeout(r, 100));
    client.close();
    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({
      marketId: "m1",
      address: "0xabc",
      sizeUsdc: 250,
      side: "buy",
      price: 0.55,
    });
  });

  it("reconnects on drop with exponential backoff", async () => {
    let connectCount = 0;
    server = new WebSocketServer({ port: 18762 });
    server.on("connection", () => {
      connectCount++;
    });

    const client = createPolymarketWsClient({
      url: "ws://127.0.0.1:18762",
      onTrade: () => {},
      onError: () => {},
      reconnectInitialMs: 50,
      reconnectMaxMs: 500,
    });
    await client.connect();
    // Forcefully terminate all existing connections so the client gets a close event,
    // then close the server to stop accepting new connections.
    for (const ws of server.clients) ws.terminate();
    server.close();
    await new Promise((r) => setTimeout(r, 100));
    server = new WebSocketServer({ port: 18762 });
    server.on("connection", () => connectCount++);
    await new Promise((r) => setTimeout(r, 700));
    client.close();
    expect(connectCount).toBeGreaterThanOrEqual(2);
  });
});
