# Polymarket Trader 配置文档

## 配置文件位置

系统按以下顺序查找配置文件：

1. `POLYMARKET_TRADER_CONFIG` 环境变量指定的路径
2. `./config.json` (当前目录)
3. `./polymarket-trader.json` (当前目录)
4. `~/.polymarket-trader/config.json`

## 配置文件格式

配置文件为 JSON 格式，支持注释（以 `//` 开头的行会被忽略）。

```bash
# 复制模板并编辑
cp config.json.template config.json
# 编辑 config.json 自定义配置
```

## 环境变量

所有配置项都可以通过环境变量覆盖，优先级高于配置文件。

### 交易阈值

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POLYMARKET_MIN_TRADE_USDC` | 200 | 最小单笔交易金额 (USD) |
| `POLYMARKET_MIN_NET_FLOW_USDC` | 3000 | 1分钟窗口最小净流入 (USD) |
| `POLYMARKET_MIN_UNIQUE_TRADERS` | 3 | 1分钟窗口最小独立交易者数 |
| `POLYMARKET_MIN_PRICE_MOVE` | 0.03 | 5分钟窗口最小价格变动 (3%) |
| `POLYMARKET_MIN_LIQUIDITY_USDC` | 5000 | 最小流动性 (USD) |

### 仓位管理

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POLYMARKET_MAX_POSITION_USDC` | 300 | 单笔最大仓位 (USD) |
| `POLYMARKET_MAX_OPEN_POSITIONS` | 8 | 最大同时持仓数量 |

### 风险控制

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POLYMARKET_DAILY_LOSS_HALT_PCT` | 0.02 | 日亏损熔断 (-2%) |
| `POLYMARKET_WEEKLY_LOSS_HALT_PCT` | 0.04 | 周亏损熔断 (-4%) |
| `POLYMARKET_STOP_LOSS_PCT` | 0.07 | 止损比例 (7%) |
| `POLYMARKET_TAKE_PROFIT_PCT` | 0.10 | 止盈比例 (10%) |

### WebSocket 连接

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POLYMARKET_CLOB_WS_URL` | wss://ws-subscriptions-clob.polymarket.com/ws/market | CLOB Market WebSocket |
| `POLYMARKET_ACTIVITY_WS_URL` | wss://ws-live-data.polymarket.com | RTDS Activity WebSocket |

### LLM 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POLYMARKET_ANALYZER_MODEL` | claude-opus-4 | Analyzer LLM 模型 |
| `POLYMARKET_LLM_TIMEOUT_MS` | 30000 | LLM 调用超时 (毫秒) |

### 数据库路径

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POLYMARKET_TRADER_DB` | `{workspaceDir}/data.db` | SQLite 数据库路径 |

## 完整配置示例

```json
{
  "minTradeUsdc": 200,
  "minNetFlow1mUsdc": 3000,
  "minUniqueTraders1m": 3,
  "minPriceMove5m": 0.03,
  "minLiquidityUsdc": 5000,
  "minTimeToResolveSec": 1800,
  "maxTimeToResolveSec": 21600,

  "staticDeadZone": [0.60, 0.85],

  "botBurstCount": 10,
  "botBurstWindowMs": 1000,

  "largeSingleTradeUsdc": 5000,
  "largeNetFlowUsdc": 10000,

  "kellyMultiplier": 0.25,
  "minPositionUsdc": 50,
  "maxPositionUsdc": 300,
  "maxSingleTradeLossUsdc": 50,

  "maxTotalPositionUsdc": 2000,
  "maxOpenPositions": 8,
  "gasPerTradeUsdc": 0.20,

  "stopLossPctNormal": 0.07,
  "stopLossPctLateStage": 0.03,
  "lateStageThresholdSec": 1800,
  "takeProfitPct": 0.10,
  "maxHoldingSec": 14400,
  "expirySafetyBufferSec": 300,

  "dailyLossHaltPct": 0.02,
  "weeklyLossHaltPct": 0.04,
  "killSwitchMinTrades": 10,
  "killSwitchMaxWinRate": 0.45,
  "totalDrawdownHaltPct": 0.10,

  "paperSlippagePct": 0.005,

  "polymarketClobWsUrl": "wss://ws-subscriptions-clob.polymarket.com/ws/market",
  "polymarketActivityWsUrl": "wss://ws-live-data.polymarket.com",

  "marketBlacklistSubstrings": ["up or down"],

  "llmTimeoutMs": 30000,
  "analyzerModel": "claude-opus-4"
}
```

## 快速调整建议

### 保守模式（适合初期）
```bash
export POLYMARKET_MIN_NET_FLOW_USDC=5000      # 提高净流入门槛
export POLYMARKET_MIN_UNIQUE_TRADERS=5        # 提高交易者数门槛
export POLYMARKET_MAX_POSITION_USDC=100       # 降低单笔仓位
export POLYMARKET_MAX_OPEN_POSITIONS=4        # 降低持仓数量
```

### 激进模式（适合高波动市场）
```bash
export POLYMARKET_MIN_NET_FLOW_USDC=1500      # 降低净流入门槛
export POLYMARKET_MIN_PRICE_MOVE=0.02         # 降低价格变动门槛
export POLYMARKET_MAX_POSITION_USDC=500       # 提高单笔仓位
export POLYMARKET_STOP_LOSS_PCT=0.05          # 收紧止损
```

## 验证配置

启动时会输出当前配置：
```
[polymarket-trader] Configuration loaded
[config] Override from env: POLYMARKET_MAX_POSITION_USDC
```
