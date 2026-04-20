# 多Agent交易架构系统

## 概述

本项目实现了一个基于多Agent架构的交易系统，采用模块化、松耦合的设计，支持实时交易决策、风险控制和性能分析。

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                     OrchestratorAgent                       │
│                    (编排与协调中心)                           │
└─────────────┬───────────────────────────────────────────────┘
              │
    ┌─────────┴──────────┬───────────────┬──────────────┐
    │                    │               │              │
┌───▼────┐        ┌────▼────┐    ┌────▼────┐   ┌────▼────┐
│Strategy│        │Execution│    │  Risk   │   │Analytics│
│ Agent  │        │ Agent   │    │ Agent   │   │ Agent   │
└────────┘        └─────────┘    └─────────┘   └─────────┘
```

### Agent职责说明

#### 1. StrategyAgent（策略Agent）
- **职责**：制定交易决策（买什么、何时买、买多少）
- **输入**：市场数据、外部信号、资金流分析
- **输出**：交易意图（买入/卖出信号）
- **状态**：持仓状态、历史决策记录

#### 2. ExecutionAgent（执行Agent）
- **职责**：执行策略Agent的决策（下单、撤单、调整）
- **输入**：交易意图、当前市场状态
- **输出**：实际订单、执行结果
- **优化**：TWAP、滑点控制、分批执行

#### 3. RiskAgent（风控Agent）
- **职责**：监控和干预风险（止损、仓位限制、熔断）
- **输入**：实时价格、持仓状态、外部事件
- **输出**：风险警报、强制操作
- **权限**：可强制平仓、暂停交易

#### 4. AnalyticsAgent（分析Agent）
- **职责**：数据分析和策略优化（回测、性能分析、信号评估）
- **输入**：历史数据、交易记录、市场数据
- **输出**：策略评分、优化建议、预测模型
- **特点**：非实时，离线分析为主

#### 5. OrchestratorAgent（编排Agent）
- **职责**：协调各Agent之间的协作，管理生命周期
- **功能**：系统级事件处理，监控系统健康状态
- **特点**：中央协调者，具有全局视野

### 通信协议

#### 消息格式

```python
# 基础消息
class BaseMessage:
    msg_id: str              # 消息唯一ID
    msg_type: str            # 消息类型
    timestamp: datetime      # 时间戳
    sender: str             # 发送者
    recipient: str          # 接收者（空为广播）
    correlation_id: str     # 关联ID（请求-响应）
    priority: MessagePriority
    metadata: Dict[str, Any]
```

#### 消息类型

| 消息类型 | 说明 | 发送者 | 接收者 |
|---------|------|--------|--------|
| MarketData | 市场数据 | 外部源 | 所有Agent |
| TradingSignal | 交易信号 | StrategyAgent | ExecutionAgent |
| OrderIntent | 订单意图 | StrategyAgent | ExecutionAgent |
| OrderResult | 订单结果 | ExecutionAgent | StrategyAgent/RiskAgent |
| PositionUpdate | 持仓更新 | PositionManager | 所有Agent |
| RiskAlert | 风险警报 | RiskAgent | 所有Agent |
| RiskAction | 风控动作 | RiskAgent | ExecutionAgent |
| AnalysisResult | 分析结果 | AnalyticsAgent | StrategyAgent |
| Heartbeat | 心跳 | 所有Agent | OrchestratorAgent |
| AgentStatus | Agent状态 | 所有Agent | OrchestratorAgent |

#### 通信模式

1. **发布-订阅（Pub/Sub）**
   - 市场数据广播
   - 风险警报广播
   - Agent状态更新

2. **点对点（P2P）**
   - 订单意图传递
   - 执行结果反馈
   - 风控指令

3. **请求-响应（Request-Response）**
   - 分析任务提交
   - 配置查询
   - 状态检查

### 状态管理

#### 全局状态

```python
class GlobalState:
    # 持仓状态
    positions: Dict[str, Position]

    # 资金状态
    available_capital: float
    total_equity: float

    # 风险指标
    daily_pnl: float
    max_drawdown: float
    var_95: float

    # 系统状态
    trading_enabled: bool
    system_mode: str
```

#### 状态同步机制

1. **事件驱动同步**
   - 订单成交事件 -> 更新持仓
   - 价格更新事件 -> 更新盈亏

2. **定时同步**
   - 每秒同步持仓状态
   - 每分钟同步风险指标

3. **冲突解决**
   - 时间戳优先
   - 风控Agent决定优先级
   - 乐观锁机制

### 监控和日志

#### Agent健康检查

```python
class HealthCheck:
    agent_id: str
    timestamp: datetime
    status: str  # healthy, warning, error

    # 指标
    cpu_usage: float
    memory_usage: float
    queue_depth: int

    # 业务指标
    messages_processed: int
    errors_count: int
    avg_latency_ms: float
```

#### 决策链路追踪

```python
class DecisionTrace:
    trace_id: str
    timestamp: datetime

    # 决策链
    steps: List[DecisionStep]

    # 输入
    market_data: MarketData
    signals: List[TradingSignal]

    # 输出
    final_decision: OrderIntent
    execution_result: OrderResult
```

## 使用示例

### 1. 初始化系统

```python
import asyncio
from agents.agents.orchestrator_agent import OrchestratorAgent, OrchestratorConfig
from agents.config.settings import get_settings

async def main():
    # 加载配置
    settings = get_settings()

    # 创建编排Agent
    config = OrchestratorConfig(
        system_config=settings.system_config
    )
    orchestrator = OrchestratorAgent(config)

    # 初始化
    await orchestrator.initialize()

    # 启动
    await orchestrator.start()

    # 运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await orchestrator.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. 发送交易信号

```python
from agents.protocol.messages import TradingSignal, OrderIntent
from agents.protocol.constants import SignalType, OrderSide, OrderType

# 创建交易信号
signal = TradingSignal(
    msg_id="signal_001",
    msg_type="trading_signal",
    sender="strategy_001",
    strategy_id="trend_following_v1",
    signal_type=SignalType.BUY,
    token_id="BTC-USD",
    confidence=0.85,
    price_target=50000.0,
    stop_loss=45000.0,
    take_profit=55000.0,
    size_recommendation=1.0,
    reasoning="Uptrend confirmed with volume support"
)

# 发送信号
await strategy_agent.send_message(signal)
```

### 3. 执行回测

```python
from datetime import datetime, timedelta

# 运行回测
result = await analytics_agent.run_backtest(
    strategy_id="trend_following_v1",
    start_date=datetime.now() - timedelta(days=365),
    end_date=datetime.now(),
    initial_capital=10000.0
)

# 输出结果
print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| AGENT_MODE | 系统模式 | autonomous |
| TRADING_ENABLED | 是否启用交易 | False |
| LOG_LEVEL | 日志级别 | INFO |
| MAX_DAILY_LOSS | 最大日亏损 | -0.05 |
| MAX_DRAWDOWN | 最大回撤 | -0.10 |

### 配置文件示例

```yaml
# config.yaml
system:
  mode: supervised
  trading_enabled: true

agents:
  strategy:
    min_confidence_threshold: 0.7
    max_signals_per_minute: 5

  execution:
    max_concurrent_orders: 10
    enable_order_splitting: true

  risk:
    max_daily_loss: -0.05
    auto_close_on_stop_loss: true

  analytics:
    enable_persistent_storage: true
    max_concurrent_analyses: 3

monitoring:
  enable: true
  metrics_endpoint: /metrics
```

## 扩展开发

### 创建自定义Agent

```python
from agents.core.agent_base import Agent, AgentConfig
from agents.protocol.messages import BaseMessage

class MyCustomAgent(Agent):
    """自定义Agent示例"""

    def __init__(self, config: AgentConfig):
        super().__init__(config)

    async def _initialize(self):
        """初始化逻辑"""
        # 初始化代码
        pass

    async def _process_message(self, message: BaseMessage):
        """消息处理逻辑"""
        # 处理收到的消息
        pass

    async def _run(self):
        """主运行逻辑"""
        while self._running:
            # 执行周期性任务
            await asyncio.sleep(1)
```

## 故障排查

### 常见问题

1. **Agent启动失败**
   - 检查配置是否正确
   - 查看日志中的错误信息
   - 确保依赖项已安装

2. **消息传递失败**
   - 检查消息总线是否正常运行
   - 验证消息格式是否正确
   - 检查Agent是否已注册

3. **性能问题**
   - 检查消息队列长度
   - 监控Agent的CPU和内存使用
   - 调整并发设置

### 调试技巧

```python
# 启用详细日志
import logging
logging.getLogger("agents").setLevel(logging.DEBUG)

# 检查Agent状态
agent_info = orchestrator.get_agent_info()
print(agent_info)

# 监控消息流
message_bus.subscribe("all", lambda msg: print(f"Message: {msg}"))
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！
