// 测试 Polymarket WebSocket 端点
import WebSocket from "ws";
import { HttpsProxyAgent } from "https-proxy-agent";

const PROXY_URL = process.env.https_proxy || process.env.HTTPS_PROXY || "http://127.0.0.1:7890";

const ENDPOINTS = [
  { name: "RTDS (activity)", url: "wss://ws-live-data.polymarket.com", type: "rtds" },
  { name: "CLOB (market)", url: "wss://ws-subscriptions-clob.polymarket.com/ws/market", type: "clob" },
];

function testEndpoint(name, url, type) {
  return new Promise((resolve) => {
    console.log(`\n[${name}] 测试: ${url}`);
    const ws = new WebSocket(url, { agent: new HttpsProxyAgent(PROXY_URL) });
    let receivedData = false;
    const timeout = setTimeout(() => {
      if (!receivedData) {
        console.log(`[${name}] ❌ 超时，未收到数据`);
        ws.close();
        resolve({ name, success: false, error: "timeout" });
      }
    }, 10000);

    ws.on("open", () => {
      console.log(`[${name}] ✅ 连接成功`);

      let subscribeMsg;
      if (type === "rtds") {
        // RTDS 订阅格式
        subscribeMsg = {
          action: "subscribe",
          subscriptions: [
            {
              topic: "activity",
              type: "trades",
              filters: ""
            }
          ]
        };
      } else {
        // CLOB Market 订阅格式 - 使用示例 asset_id
        subscribeMsg = {
          assets_ids: ["21742633143463906290569050155826241533067272736897614950488156847949938836455"],
          type: "market"
        };
      }
      ws.send(JSON.stringify(subscribeMsg));
      console.log(`[${name}] 📤 发送订阅: ${JSON.stringify(subscribeMsg)}`);
    });

    ws.on("message", (data) => {
      try {
        const parsed = JSON.parse(data.toString());
        if (!receivedData) {
          receivedData = true;
          console.log(`[${name}] ✅ 收到数据:`);
          console.log(JSON.stringify(parsed, null, 2));
          clearTimeout(timeout);
          ws.close();
          resolve({ name, success: true, sample: parsed });
        }
      } catch (e) {
        console.log(`[${name}] ⚠️ 收到非 JSON 数据: ${data.toString().slice(0, 100)}`);
      }
    });

    ws.on("error", (err) => {
      console.log(`[${name}] ❌ 错误: ${err.message}`);
      clearTimeout(timeout);
      resolve({ name, success: false, error: err.message });
    });

    ws.on("close", () => {
      if (!receivedData) {
        console.log(`[${name}] ⚠️ 连接关闭，未收到数据`);
      }
    });
  });
}

async function main() {
  console.log("=== Polymarket WebSocket 端点测试 ===\n");

  for (const endpoint of ENDPOINTS) {
    await testEndpoint(endpoint.name, endpoint.url, endpoint.type);
    // 等待 2 秒再测试下一个
    await new Promise(r => setTimeout(r, 2000));
  }

  console.log("\n=== 测试完成 ===");
  process.exit(0);
}

main();
