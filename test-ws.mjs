// 测试 Polymarket WebSocket 端点
import WebSocket from "ws";

const ENDPOINTS = [
  { name: "CLOB", url: "wss://ws-subscriptions-clob.polymarket.com/ws/" },
  { name: "Activity", url: "wss://ws.polymarket.com" },
];

function testEndpoint(name, url) {
  return new Promise((resolve) => {
    console.log(`\n[${name}] 测试: ${url}`);
    const ws = new WebSocket(url);
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
      // 发送订阅消息
      ws.send(JSON.stringify({ type: "SUBSCRIBE", channel: "market" }));
      console.log(`[${name}] 📤 发送订阅: {"type":"SUBSCRIBE","channel":"market"}`);
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
    await testEndpoint(endpoint.name, endpoint.url);
    // 等待 2 秒再测试下一个
    await new Promise(r => setTimeout(r, 2000));
  }

  console.log("\n=== 测试完成 ===");
  process.exit(0);
}

main();
