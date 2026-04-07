# Polymarket Trader 桌面应用 — 设计文档

**日期**：2026-04-07
**状态**：v1 草案，待用户审阅
**前置 spec**：`docs/specs/2026-04-06-polymarket-trading-agents-design.md`（交易引擎设计）
**前置 plan**：`docs/plans/2026-04-06-polymarket-trader-plugin.md`（已实现的引擎，48 commits, 160 tests pass）

---

## 1. 背景与目标

### 1.1 为什么要做桌面应用

现有 polymarket-trader 项目已经实现了完整的交易引擎（Collector、Executor、Reviewer 等），160 个测试全过，但**没有真正可用的入口**：

- `AgentInvoker` 是抛错的 stub，无法实际触发 Analyzer
- 没有 UI 看仓位、PnL、调配置
- 用户必须手动改代码、看 SQLite、读 markdown 文件
- 任何想配置交易行为的事都要重新 build

桌面应用就是要把这些**全部解决**：让用户**双击启动 → 配 LLM key → 跑起来 → 看到一切**。

### 1.2 核心目标

| 目标 | 衡量标准 |
|------|---------|
| **真正可用** | 全新用户从下载到第一笔 paper 交易 < 10 分钟 |
| **完全独立** | 不依赖 dlxiaclaw、不依赖外部 OpenClaw runtime、不依赖 RivonClaw |
| **可视化** | 持仓、PnL、Reviewer 报告、Coordinator 简报全部 UI 可见 |
| **可对话** | 3 个 agent 员工（Analyzer / Reviewer / Risk Manager）支持自然语言交互 |
| **可自我进化** | Reviewer 高置信度建议自动 apply，Coordinator 每小时主动思考 |
| **跨平台** | Windows / macOS / Linux 都能跑 |

### 1.3 非目标（YAGNI 严格）

- ❌ **多用户 / 云同步**：单机单用户
- ❌ **回测系统**：spec §1.2 已砍，仍砍
- ❌ **手机 / 移动端**：只桌面
- ❌ **真实下单到 Polymarket 链上**：v1 仍 paper trading（spec §1.2 一致）
- ❌ **自动 OAuth 服务器**：自动更新放 Phase 2
- ❌ **代码签名**：v1 用未签名（GitHub Releases），文档说明绕过警告
- ❌ **多账户切换**：单 LLM provider 配置
- ❌ **多策略 / Bandit**：spec §1.2 一致，仍单策略 smart_money_flow

---

## 2. 架构概览

### 2.1 仓库结构（monorepo 改造）

```
polymarket-trader/                          # 同一个 git repo,保留全部 48 commits 历史
├── package.json                            # workspaces root
├── pnpm-workspace.yaml                     # 新增
├── tsconfig.base.json                      # 提升到 root
├── electron-builder.config.json            # 新增
│
├── packages/
│   ├── engine/                             # 现有 src/* 整体搬过来,160 tests 继续跑
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── collector/                  # WS 订阅 + 滚动窗口 + 触发器
│   │   │   ├── executor/                   # Kelly + 4 路出场 + 熔断
│   │   │   ├── db/                         # SQLite + 7 张表 repos
│   │   │   ├── bus/                        # 类型化 event bus
│   │   │   ├── config/                     # TraderConfig schema + defaults
│   │   │   ├── recovery/                   # startup recovery
│   │   │   ├── reviewer/                   # statistics, kill-switch, report-generator
│   │   │   ├── analyzer/                   # verdict-parser, context-packer (analyzer-client 砍掉)
│   │   │   └── util/                       # time helpers, typed errors
│   │   └── tests/                          # 160 现有测试
│   │
│   ├── llm/                                # 新建:provider 抽象层
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── provider.ts                 # LlmProvider 接口
│   │   │   ├── adapters/
│   │   │   │   ├── openai-compat.ts        # 基类:覆盖 19 个 OpenAI 兼容 provider
│   │   │   │   ├── anthropic.ts            # API key + Subscription (CLI 凭证检测)
│   │   │   │   ├── gemini.ts               # API key + Google OAuth
│   │   │   │   ├── bedrock.ts              # AWS Bedrock
│   │   │   │   └── ollama.ts               # 本地 HTTP
│   │   │   ├── registry.ts                 # 用户配置的 active provider 列表
│   │   │   ├── routing.ts                  # "Prefer Subscription" 路由策略
│   │   │   └── runners/
│   │   │       ├── analyzer-runner.ts      # 替代 stub,真正调 LLM 判断 trigger
│   │   │       ├── reviewer-runner.ts      # 调 LLM 复盘
│   │   │       ├── risk-mgr-runner.ts      # 主动 + 被动两模式
│   │   │       └── personas/                # 3 个 agent 的 system prompt 模板
│   │   └── tests/
│   │
│   ├── main/                                # 新建:Electron 主进程
│   │   ├── package.json
│   │   ├── src/
│   │   │   ├── index.ts                    # Electron app entry
│   │   │   ├── tray.ts                     # 系统托盘 + 快速状态
│   │   │   ├── window.ts                   # 主窗口管理
│   │   │   ├── ipc.ts                      # IPC handlers (renderer ↔ engine)
│   │   │   ├── lifecycle.ts                # bootEngine() / shutdownEngine()
│   │   │   ├── coordinator.ts              # 每小时调度 Risk Mgr 的主动 brief
│   │   │   ├── reviewer-scheduler.ts       # 每日调度 Reviewer
│   │   │   ├── auto-apply.ts               # 高置信度 filter_proposals 自动 apply
│   │   │   ├── secrets.ts                  # Electron safeStorage 包装 (OS keychain)
│   │   │   └── notifications.ts            # 桌面通知 + 托盘 alert
│   │   └── tests/
│   │
│   └── renderer/                            # 新建:React UI
│       ├── package.json
│       ├── vite.config.ts
│       ├── index.html
│       ├── DESIGN.md                        # 从 awesome-design-md 复制 (kraken)
│       ├── src/
│       │   ├── main.tsx
│       │   ├── App.tsx                      # 4 page React Router
│       │   ├── pages/
│       │   │   ├── Dashboard.tsx
│       │   │   ├── Settings.tsx
│       │   │   ├── Reports.tsx
│       │   │   └── Chat.tsx
│       │   ├── components/                  # 全部按 DESIGN.md 风格自写
│       │   │   ├── Sidebar.tsx
│       │   │   ├── PositionTable.tsx
│       │   │   ├── KpiCard.tsx
│       │   │   ├── CoordinatorBanner.tsx
│       │   │   ├── ProviderCard.tsx
│       │   │   ├── ProposalCard.tsx
│       │   │   ├── ReportListItem.tsx
│       │   │   ├── BucketTable.tsx
│       │   │   ├── ChatMessage.tsx
│       │   │   ├── ChatInput.tsx
│       │   │   └── EmployeeTab.tsx
│       │   ├── stores/                      # Zustand
│       │   │   ├── portfolioStore.ts
│       │   │   ├── positionsStore.ts
│       │   │   ├── chatStore.ts
│       │   │   └── coordinatorStore.ts
│       │   ├── ipc-client.ts                # typed wrapper over window.pmt
│       │   └── styles/                      # Kraken 主题变量
│       └── tests/
│
├── docs/
│   ├── specs/
│   │   ├── 2026-04-06-polymarket-trading-agents-design.md  # 引擎 spec (已有)
│   │   └── 2026-04-07-desktop-app-design.md                # 本文档
│   └── plans/
│       ├── 2026-04-06-polymarket-trader-plugin.md          # 已实现 (engine)
│       ├── 2026-04-07-desktop-app-plan.md                  # 待写
│       └── I1-I2-findings.md                               # 历史调研
│
└── README.md
```

### 2.2 关键删除清单

要从现有 `src/` 砍掉的代码：

| 文件 | 删除原因 |
|------|---------|
| `src/index.ts` (旧 plugin entry) | 改为 `packages/main/src/index.ts` (Electron app entry) |
| `src/plugin-sdk.ts` (OpenClaw plugin SDK shim) | 不再做 OpenClaw plugin,30 行 inline SDK 完全用不上 |
| `src/analyzer/analyzer-client.ts` 的 stub 实现 | 改写到 `packages/llm/runners/analyzer-runner.ts`,真正调 LLM |

### 2.3 技术栈

| 层 | 技术 | 备注 |
|----|------|------|
| 引擎 | TypeScript + Node.js 24+, better-sqlite3, ws | 现有,不变 |
| LLM | @anthropic-ai/sdk, openai (兼容协议), @google/generative-ai, @aws-sdk/client-bedrock-runtime, ollama | 5 个 SDK 支持 24+ provider |
| 桌面壳 | Electron 30+ | 跨平台标配 |
| 主进程 | TypeScript, Electron API, electron safeStorage | safeStorage 全平台 OS keychain |
| 渲染进程 | React 18 + Vite 5 + TypeScript | 现代标配 |
| 状态管理 | Zustand | 轻量,不像 Redux 那么重 |
| 路由 | React Router 7 | 标配 |
| UI 库 | **不用现成的**,按 DESIGN.md 风格自写 components | 保持视觉一致性 |
| 图表 | Recharts | PnL 曲线 |
| 打包 | electron-builder | 跨平台标配 |
| 测试 | vitest + @testing-library/react | 与现有引擎一致 |

---

## 3. 数据流 + LLM 调度

### 3.1 完整交易筛选流水线（13 步)

每条 WS 成交事件进来后,要过 **13 道关卡**才有可能开仓:

```
[1]  Polymarket WS Client          # ws-client.ts 解析 raw event
[2]  单笔金额过滤 ≥ $200            # 否则丢
[3]  机器人过滤                     # bot-filter.ts: 同地址 1s>10 笔标记 bot
[4]  写入 1m / 5m 滚动窗口          # rolling-window.ts
[5]  触发条件评估 (9 条)            # trigger-evaluator.ts:
       • 黑名单 market 标题
       • 非死亡区间 [0.60, 0.85]
       • 30 分钟 ≤ time_to_resolve ≤ 72h
       • 流动性 ≥ $5000
       • 5m 价格变动 ≥ 3%
       • 1m 净流入 ≥ $3000
       • 1m 独立 trader ≥ 3
[6]  大单豁免检查                   # 单笔 ≥$5000 OR 净流入 ≥$10000 → 跳过 trader 数检查
[7]  发布 TriggerEvent → Event Bus
[8]  🤖 LLM CALL #1: Analyzer       # analyzer-runner.ts: 调 LLM,30s 超时,解析 verdict JSON
[9]  Executor 准入检查 (7 道)       # executor.ts:
       • 日内/周/总回撤熔断
       • 策略 kill_switch
       • 总仓位上限 $2000
       • 持仓数 ≤ 8
       • 该 market conflict lock
[10] Kelly 仓位计算                 # kelly.ts: 1/4 Kelly + 单笔最大损失 $50
[11] PaperExecutor 开仓             # paper-fill.ts: mid + slippage,写 signal_log
[12] 持仓监控循环                   # exit-monitor.ts: E/A-SL/A-TP/D/C 4 路出场
[13] 平仓 + PnL 计算 + 状态更新     # close-position: 释放 lock,更新 portfolio_state
```

**关键**:此流水线**完全是现有引擎代码**,新桌面应用只是把 Step 8 的 stub 替换成真实 LLM 调用,其他不动。

### 3.2 LLM 4 类调度方式

| # | 方式 | 触发 | 频率 | 默认模型 | 日成本估算 |
|---|------|------|------|---------|----------|
| 1 | **事件驱动** | 每个 trigger 命中 → Analyzer | 5-20 次/天 | claude-opus-4-6 | ~$0.50 |
| 2 | **每日定时** | setInterval 24h → Reviewer | 1 次/天 | claude-sonnet-4-6 | ~$0.07 |
| 3 | **每小时定时** | setInterval 1h → Risk Mgr / Coordinator | 24 次/天 | claude-haiku-4-5 | ~$0.12 |
| 4 | **用户主动** | Chat 页面 → 任一 agent | 不可预测 | 跟随 agent default | ~$0.10 |
| | | | | **总计** | **~$0.79/天 ≈ $24/月** |

如果用 Anthropic Subscription / Gemini Free Tier,**实际成本可降到 $0**。Routing strategy 默认 "Prefer Subscription"。

### 3.3 自主进化机制（4 个触发点）

| 进化点 | 触发条件 | 自动 / 人审 |
|-------|---------|-----------|
| **Kelly 用新胜率** | Reviewer 跑完更新 strategy_performance | ✅ 全自动,下一笔即用 |
| **kill_switch 熔断** | 连续 10 笔胜率 < 45% | ✅ 全自动,立即停 |
| **filter_proposals 高置信度自动 apply** | 样本 ≥ 30 + 预期胜率提升 ≥ 5% + 不影响最大单笔损失 | ✅ 自动 apply + audit log + 24h 内可 rollback |
| **filter_proposals 低置信度** | 不满足上述 | ⚠️ 进 pending,Settings 红点提醒,等人 approve |

### 3.4 Coordinator —— Risk Manager 升级版

普通 Risk Manager 是**只读 LLM 包装**(用户提问时回答)。升级后增加**主动模式**:

- 每小时由 `packages/main/src/coordinator.ts` 的 setInterval 触发
- 读全部状态(portfolio_state, 最近 1h signal_log, 最近 reject 历史, market 整体活跃度)
- 调 LLM 思考,输出 JSON `{summary, alerts[], suggestions[]}`
- 写入 `coordinator_log` 表
- 桌面通知 / 托盘弹窗(critical alert 时)
- Dashboard 顶部显示最新 summary

**关键**:Coordinator **不直接改任何配置**,只观察 + 提建议 + 主动通知。所有配置改动必须经过 filter_proposals 人审或自动 apply 通道,**不允许 Coordinator 绕过这套机制**。

---

## 4. UI 设计

### 4.1 风格 —— Kraken DESIGN.md

视觉风格基于 [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) 仓库的 **kraken** DESIGN.md(per spec §1.1.5 约定)。

关键设计变量:

- **主色**:Kraken Purple `#7132f5`
- **背景**:白色 `#ffffff`
- **文字**:近黑 `#101114`,次级灰 `#9497a9`
- **盈利**:绿色 `#149e61`
- **亏损**:红色 `#d63b3b`
- **NO 仓位**:深紫 `#5b1ecf`
- **圆角**:按钮 12px,卡片 12px,标签 6-8px
- **阴影**:`rgba(0,0,0,0.03) 0px 4px 24px` (whisper-level)
- **字体**:IBM Plex Sans / Helvetica Neue (kraken-brand 字体非免费,降级到开源)

### 4.2 4 个页面 + sidebar

```
┌────────────┬─────────────────────────────────────────┐
│ Sidebar    │  Main Content (varies by page)          │
│ 220px      │                                         │
│            │                                         │
│ Pages:     │                                         │
│  Dashboard │                                         │
│  Settings  │                                         │
│  Reports   │                                         │
│  Chat      │                                         │
│            │                                         │
│ Employees: │                                         │
│  🧠 Analyzer│                                         │
│  📊 Reviewer│                                         │
│  🛡️ Risk Mgr│                                         │
└────────────┴─────────────────────────────────────────┘
```

#### 4.2.1 Dashboard

- 顶部 **Coordinator brief 横幅**(紫色边)显示最新简报
- **4 个 KPI 卡片**:Equity / Open Positions / 7d Win Rate / Drawdown
- **Open Positions 实时表**:market title, side, entry, now, size, PnL, 持仓时长
- 按钮:Run Reviewer Now / Pause Trading / Emergency Stop

#### 4.2.2 Settings

4 个 section:

1. **🤖 LLM Providers**:
   - Tab 切换 All (24) / API Key (16) / Subscription (7) / Local (1) / Connected only
   - 每个 provider 卡片:状态、key 末 4 位、连接按钮
   - **每个 agent 独立选模型**(Analyzer / Reviewer / Risk Mgr 可用不同 provider)
   - **Routing strategy** 默认 "Prefer Subscription",quota 用完 fallback API key
2. **⚡ Trading Thresholds**:每行 edit,被 auto-apply 的有绿标
3. **🛡️ Risk Limits**:capital, max position, max loss, halt thresholds
4. **📝 Pending Filter Proposals**:Reviewer 待审建议,Approve / Reject 按钮

#### 4.2.3 Reports

- 左 280px **历史报告列表**(按日期,带 PnL 颜色)
- 右 **报告详情**:3 KPI + 按桶统计表 + Reviewer notes + 提案列表
- 底部脚注:原 markdown 文件路径

#### 4.2.4 Chat

- 左 60px **3 员工头像 tab**(点击切换 conversation)
- 右 **conversation 区域**:
  - 顶部 header:agent 头像 + 名称 + online 状态 + 用的模型 + provider
  - 消息流:用户气泡(右紫色) vs agent 气泡(左白底带头像)
  - **Coordinator 自动 brief**(系统消息,紫边横幅,在 Risk Mgr 对话顶部)
  - 流式 response(token 逐个出现)
  - 底部 input + 权限说明("Risk Mgr 只读,不能改配置")

### 4.3 LLM Provider 完整列表（24 个）

按适配器复用分组,**5 个 adapter 代码 → 25 个 provider 入口**:

| Adapter | 覆盖 provider | 个数 |
|---------|-------------|------|
| **OpenAICompatibleAdapter** (基类) | DeepSeek, Zhipu, Moonshot, Qwen, Groq, Mistral, xAI, OpenRouter, MiniMax, Venice AI, Xiaomi MiMo, Volcengine, NVIDIA NIM, OpenAI, Zhipu Coding, Qwen Coding, Kimi Code, MiniMax Coding, Volcengine Coding | 19 |
| **AnthropicAdapter** | Anthropic API key + Anthropic Subscription (CLI credentials) | 2 |
| **GeminiAdapter** | Gemini API key + Google OAuth (free tier) | 2 |
| **BedrockAdapter** | AWS Bedrock (uses AWS SDK) | 1 |
| **OllamaAdapter** | Local Ollama (HTTP) | 1 |
| **总计** | | **25** |

OpenAI 兼容协议是当前业界事实标准,绝大多数 provider 直接套用同一份代码,只是 base URL 和模型列表不同。

---

## 5. 数据模型 + IPC

### 5.1 数据库改动（在现有 7 张表基础上新增 4 张)

```
~/.polymarket-trader/data.db
├── (现有 7 张表 — 不动)
│   ├── signal_log
│   ├── strategy_performance
│   ├── filter_config
│   ├── filter_proposals
│   ├── strategy_kill_switch
│   ├── portfolio_state
│   └── schema_version
└── (新增 4 张)
    ├── chat_messages           # 用户和 3 个 agent 的对话历史
    ├── coordinator_log         # Coordinator 每小时简报
    ├── llm_provider_state      # 各 provider 连接状态、quota
    └── app_state               # 桌面 app 自身状态(窗口位置、last page 等)
```

### 5.2 新表 schema

```sql
CREATE TABLE chat_messages (
  message_id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT NOT NULL CHECK (agent_id IN ('analyzer', 'reviewer', 'risk_manager')),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  model_used TEXT,
  provider_used TEXT,
  tokens_input INTEGER,
  tokens_output INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_chat_messages_agent ON chat_messages(agent_id, created_at DESC);

CREATE TABLE coordinator_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_at INTEGER NOT NULL,
  summary TEXT NOT NULL,
  alerts TEXT NOT NULL DEFAULT '[]',          -- JSON
  suggestions TEXT NOT NULL DEFAULT '[]',     -- JSON
  context_snapshot TEXT NOT NULL,             -- JSON
  model_used TEXT,
  tokens_total INTEGER
);
CREATE INDEX idx_coordinator_log_time ON coordinator_log(generated_at DESC);

CREATE TABLE llm_provider_state (
  provider_id TEXT PRIMARY KEY,
  is_connected INTEGER NOT NULL DEFAULT 0,
  auth_type TEXT NOT NULL,                    -- 'api_key' / 'oauth' / 'cli_credential' / 'aws'
  models_available TEXT NOT NULL DEFAULT '[]',
  quota_used INTEGER DEFAULT 0,
  quota_limit INTEGER,
  quota_resets_at INTEGER,
  last_check_at INTEGER NOT NULL,
  last_error TEXT
);

CREATE TABLE app_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

### 5.3 敏感数据存储

API key / OAuth token **不存 SQLite**,存 OS keychain:

- Windows: DPAPI (via Electron `safeStorage` API)
- macOS: Keychain (via Electron `safeStorage` API)
- Linux: libsecret / kwallet (via Electron `safeStorage` API)

**Electron 自带的 `safeStorage` API** 全平台覆盖,零额外依赖。

### 5.4 IPC 架构

```
┌──────────────────────────────────────────────────────┐
│  Electron Main Process (Node.js)                     │
│   • 直接 import packages/engine/* 模块               │
│   • 直接 import packages/llm/* 模块                  │
│   • 启动 Collector / Executor / 调度 Reviewer        │
│   • 调度 Coordinator (每小时)                         │
│   • IPC handlers (ipcMain.handle / ipcMain.on)      │
│   • 向 Renderer 推送事件 (webContents.send)          │
└────────────────┬─────────────────────────────────────┘
                 │ IPC
                 ▼
┌──────────────────────────────────────────────────────┐
│  preload.js (sandboxed bridge)                       │
│   contextBridge.exposeInMainWorld('pmt', { ... })    │
│   仅暴露 typed 安全 API,不暴露原始 ipcRenderer       │
└────────────────┬─────────────────────────────────────┘
                 │ window.pmt.xxx()
                 ▼
┌──────────────────────────────────────────────────────┐
│  Electron Renderer Process (Chromium + React)        │
│   • 4 页 UI                                          │
│   • Zustand stores                                   │
│   • 订阅 IPC 事件,实时更新                           │
│   • 通过 window.pmt 调用 main 端                     │
└──────────────────────────────────────────────────────┘
```

### 5.5 IPC API（typed,renderer 端通过 window.pmt 调用）

**Renderer → Main**(请求/响应,用 invoke):

```typescript
window.pmt = {
  // Portfolio
  getPortfolioState(): Promise<PortfolioState>,
  getOpenPositions(): Promise<SignalLogRow[]>,
  getRecentClosedTrades(limit: number): Promise<SignalLogRow[]>,

  // Coordinator
  getLatestCoordinatorBrief(): Promise<CoordinatorLog | null>,
  triggerCoordinatorNow(): Promise<CoordinatorLog>,

  // Reviewer
  getRecentReports(limit: number): Promise<ReportSummary[]>,
  getReportContent(reportPath: string): Promise<string>,
  triggerReviewerNow(): Promise<ReviewerRunResult>,

  // Filter proposals
  getPendingProposals(): Promise<FilterProposalRow[]>,
  approveProposal(id: number): Promise<void>,
  rejectProposal(id: number): Promise<void>,

  // Config
  getConfig(): Promise<TraderConfig>,
  updateConfigField(key: string, value: unknown): Promise<void>,

  // LLM Providers
  listProviders(): Promise<LlmProviderState[]>,
  connectProvider(providerId: string, credentials: Credentials): Promise<void>,
  disconnectProvider(providerId: string): Promise<void>,
  setAgentModel(agentId: AgentId, providerId: string, modelId: string): Promise<void>,

  // Chat
  getChatHistory(agentId: AgentId, limit: number): Promise<ChatMessage[]>,
  sendMessage(agentId: AgentId, content: string): Promise<ChatMessage>,
  clearChatHistory(agentId: AgentId): Promise<void>,

  // Engine control
  pauseTrading(): Promise<void>,
  resumeTrading(): Promise<void>,
  emergencyStop(): Promise<void>,
};
```

**Main → Renderer**(推送事件):

```typescript
type PmtEvents = {
  'position:opened': SignalLogRow;
  'position:closed': SignalLogRow;
  'portfolio:updated': PortfolioState;
  'coordinator:brief': CoordinatorLog;
  'trigger:rejected': { market_id: string; reason: string };
  'trigger:accepted': { market_id: string; signal_id: string };
  'engine:halted': { reason: string; type: 'daily' | 'weekly' | 'total' | 'strategy' };
  'engine:resumed': { type: 'daily' | 'weekly' | 'total' | 'strategy' };
  'chat:streaming': { agent: AgentId; chunk: string };
  'chat:complete': ChatMessage;
};
```

### 5.6 流式 chat（关键 UX）

LLM chat 必须流式,不能等 30 秒一次性返回:

```
User 发送 "Are we close to halts?"
   ↓
Renderer ipcInvoke('sendMessage', ...)
   ↓
Main 收到 → 调 packages/llm 的 streamingChat
   ↓
每个 token chunk → webContents.send('chat:streaming', { chunk })
   ↓
Renderer 订阅 'chat:streaming' → 实时 append 到 message bubble
   ↓
完成 → webContents.send('chat:complete', fullMessage)
   ↓
Renderer 把消息存到 chat_messages 表 (via Main)
```

### 5.7 安全设计

- **contextIsolation: true** —— renderer 拿不到 Node API
- **nodeIntegration: false** —— renderer 是纯浏览器环境
- **preload.js** 通过 `contextBridge.exposeInMainWorld` 暴露白名单 API
- 每个 IPC handler 在 main 端**做 input validation**
- **所有 LLM 调用都在 Main 进程**(Renderer 永远拿不到 API key)

---

## 6. 分阶段交付里程碑

| Milestone | 内容 | 估计 task 数 | 交付物 |
|-----------|------|-----------|--------|
| **M1: Foundation** | Monorepo 改造 + engine 搬迁 + 4 张新表 schema + Electron safeStorage 包装 | ~10 | `pnpm install` 后 engine 测试全过 (160 tests) |
| **M2: LLM Provider Layer** | 5 个 adapter (OpenAI 兼容 / Anthropic / Gemini / Bedrock / Ollama) + provider registry + per-agent runner + 1 个 OAuth flow (Gemini) + Anthropic CLI 凭证检测 | ~18 | 24 个 provider 都能 connect/test/list models |
| **M3: Electron Main** | Electron app boot + tray + window + lifecycle + IPC scaffold + Engine 真正启动并跑 24/7 + Coordinator 调度(但还没接 LLM UI) | ~12 | 命令行能 `pnpm start`,托盘出现,引擎在跑,但没 UI |
| **M4: React UI (mocked)** | Vite + React Router + Zustand + 4 页面骨架 + DESIGN.md kraken 风格 component 库 + 用 mock 数据填表 | ~20 | UI 能跑,全部用假数据,看起来和 mockup 一致 |
| **M5: IPC Wiring** | 把 4 页 + 3 chat tab 接到真 IPC + 流式 chat + 实时 position update + Settings 改配置真生效 | ~15 | UI 显示真数据,操作真生效,**第一个真正可用的版本** |
| **M6: Coordinator + Auto-apply** | Risk Mgr / Coordinator 主动 brief + filter_proposals 高置信度自动 apply + audit log + rollback + 桌面通知 | ~12 | 系统能自主进化(受控) |
| **M7: Packaging + 稳定观察** | electron-builder 配 Win/macOS/Linux + code signing 文档 + 第一个 .exe 可双击运行 + M4-style 稳定观察期 (2-4 周 paper trading) | ~10 + 观察 | 能给别人用的安装包 + 真实数据反馈 |

**总计 ~97 task,约 7-8 周开发 + 2-4 周稳定观察**

### 6.1 关键交付节点

| 节点 | 时间 | 用户能做什么 |
|------|------|----------|
| M1 完成 | Week 1 末 | engine 跑得起来(命令行测试),但还看不到任何 UI |
| M2 完成 | Week 3 末 | 命令行能配 LLM,能 chat 一个 agent (CLI demo),但没桌面窗口 |
| M3 完成 | Week 4 末 | 双击图标启动桌面 app,**托盘有 icon**,引擎在跑,但**窗口空白** |
| M4 完成 | Week 5 末 | **看到 4 页 UI** (kraken 风格),但**全是假数据**,按钮点了没反应 |
| **M5 完成** | **Week 6 末** | **真数据 + 真操作**,能开仓能看仓能 chat —— **第一个真正可用的版本** |
| M6 完成 | Week 7 末 | Coordinator 主动 brief + 自动调参 + audit log —— **完整功能版** |
| M7 完成 | Week 8 末 | **分发版** .exe / .dmg / AppImage,给别人用没问题 |

**关键 milestone 是 M5** —— 那时候已经可以 paper trade 了,M6/M7 是锦上添花。

---

## 7. 打包 / 分发

### 7.1 工具 —— electron-builder

```
electron-builder.config.json
├── win:    target nsis (.exe installer)
├── mac:    target dmg + zip
└── linux:  target AppImage + deb
```

### 7.2 分发渠道

**v1 (M7 阶段)**:
- GitHub Releases 上传 `.exe` / `.dmg` / `.AppImage`
- 手动分发,自己用 + 朋友用

**v2 (Phase 2 候选,YAGNI)**:
- electron-updater 自动检查更新
- GitHub Releases 当更新源
- 工作量 ~3 task

**code signing**(可选):
- v1 不签名,文档说明绕过警告
- v2 考虑买证书($100-300/年 Windows + $99/年 Apple)

### 7.3 安装包大小估算

| 组件 | 大小 |
|------|------|
| Electron runtime | ~80 MB |
| React + Vite bundle | ~500 KB |
| better-sqlite3 native | ~3 MB |
| 引擎 + LLM SDKs | ~6 MB |
| **总计** | **~90-100 MB** |

---

## 8. 风险点

| 风险 | 描述 | 缓解 |
|------|------|------|
| **better-sqlite3 native build** | Electron 用的 Node 版本和系统 Node 不一致,需要 `electron-rebuild` | M3 之前测试 + 文档化 |
| **Anthropic CLI 凭证文件位置变动** | 不同版本 / 不同 OS 路径不一样 | M2 时多平台测试 |
| **Coordinator 每小时调用累积 token 成本** | 默认 Haiku 每月 ~$3.6,但可能更多 | Settings 加 "Coordinator 频率" 滑块 1h - 6h,允许用户降频 |
| **Polymarket WS 协议变更** | 引擎已经写死了字段名 | 现有单元测试 + 加 schema validation |
| **electron-builder 跨平台 build 复杂** | Windows build macOS package 需要 docker / VM | v1 三个平台分别在对应 OS 上 build |

---

## 9. 已确认的设计决定

- **核心目标**:稳定持续盈利(月 DD ≤ 5%、Sharpe ≥ 1.0),桌面 app 是为这个目标服务的工具
- **完全独立**:不依赖 dlxiaclaw、不依赖 OpenClaw runtime、不依赖任何外部桌面 app
- **代码复用**:monorepo,packages/engine = 现有 src/ + 现有 160 tests
- **技术栈**:Electron + React + Vite + Zustand + Recharts,5 个 LLM adapter (24 provider)
- **3 个员工**:Analyzer(信号判官) + Reviewer(复盘师) + Risk Mgr / Coordinator(风控+主动思考)
- **UI 风格**:Kraken DESIGN.md (per spec §1.1.5 约定)
- **4 页 + 3 员工 chat tab**
- **自主进化等级 C**:filter_proposals 高置信度自动 apply + Coordinator 主动 brief
- **系统托盘 + 后台 24/7**:关窗口最小化,引擎不停
- **流式 chat**:LLM token 逐个出现
- **存储**:SQLite 在 `~/.polymarket-trader/data.db`,API key 在 OS keychain
- **分发**:v1 GitHub Releases 手动,v2 electron-updater 自动

---

## 10. 开放问题（实现前对齐）

1. **Coordinator 频率**:默认 1h 一次,要不要做成可配(15min / 1h / 4h)?
2. **Chat history retention**:无限保留 vs 滚动 30 天?
3. **第一次启动向导**:做 "Welcome wizard" 引导填 LLM key,还是直接进 Settings?
4. **托盘菜单内容**:除了 "Show / Quit",还要加 "Pause / Resume / Status" 吗?
5. **更新通知**:M6 的 Coordinator 写报告 / kill_switch 触发 → OS 桌面通知 vs 仅 in-app?

---

## 11. 参考

- [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) - DESIGN.md 来源
- [west-garden/polymarket-agent](https://github.com/west-garden/polymarket-agent) - 旧系统(已诊断,新系统避坑)
- 现有引擎 spec: `docs/specs/2026-04-06-polymarket-trading-agents-design.md`
- 现有引擎 plan: `docs/plans/2026-04-06-polymarket-trader-plugin.md`
