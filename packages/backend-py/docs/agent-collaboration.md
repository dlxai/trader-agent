# 多智能体协作配置指南

## 概述

交易引擎采用多智能体（Multi-Agent）架构，各智能体通过事件总线（EventBus）进行异步协作。每个智能体负责特定的交易任务，通过事件订阅和发布实现松耦合协作。

## 智能体架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           MULTI-AGENT COLLABORATION ARCHITECTURE                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   EVENT BUS     │
                              │  (Message Queue)│
                              └────────┬────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   DATA COLLECTOR    │  │   SIGNAL ANALYZER   │  │   ORDER EXECUTOR    │
│     (Agent 1)       │  │     (Agent 2)       │  │     (Agent 3)       │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ 职责: 市场数据收集  │  │ 职责: 信号分析验证  │  │ 职责: 订单执行      │
│                     │  │                     │  │                     │
│ 订阅:               │  │ 订阅:               │  │ 订阅:               │
│ • None (主动推送)   │  │ • SIGNAL_GENERATED  │  │ • SIGNAL_APPROVED   │
│                     │  │                     │  │ • ORDER_SUBMITTED   │
│ 发布:               │  │ 发布:               │  │                     │
│ • MARKET_DATA_UPDATE│  │ • SIGNAL_ANALYZED   │  │ 发布:               │
│ • PRICE_TICK        │  │ • SIGNAL_APPROVED   │  │ • ORDER_CREATED     │
│ • ORDER_BOOK_UPDATE │  │ • SIGNAL_REJECTED   │  │ • ORDER_FILLED      │
│ • TRADE_UPDATE      │  │                     │  │ • ORDER_REJECTED    │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
           │                           │                           │
           └───────────────────────────┼───────────────────────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ▼                           ▼                           ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  POSITION TRACKER   │  │   RISK MANAGER      │  │  DAILY REVIEWER     │
│     (Agent 4)       │  │     (Agent 5)       │  │     (Agent 6)       │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ 职责: 持仓监控      │  │ 职责: 风险控制      │  │ 职责: 每日审查      │
│                     │  │                     │  │                     │
│ 订阅:               │  │ 订阅:               │  │ 订阅:               │
│ • ORDER_FILLED      │  │ • RISK_LIMIT_       │  │ • Daily Schedule    │
│ • POSITION_OPENED   │  │   EXCEEDED          │  │   (UTC 00:00)       │
│ • PRICE_TICK        │  │ • DAILY_LOSS_       │  │                     │
│                     │  │   LIMIT_HIT           │  │ 发布:               │
│ 发布:               │  │                     │  │ • DAILY_REPORT      │
│ • POSITION_UPDATED  │  │ 发布:               │  │ • KILL_SWITCH_      │
│ • POSITION_CLOSED   │  │ • KILL_SWITCH_      │  │   TRIGGERED         │
│ • STOP_LOSS_        │  │   TRIGGERED         │  │                     │
│   TRIGGERED         │  │                     │  │                     │
│ • TAKE_PROFIT_      │  │                     │  │                     │
│   TRIGGERED         │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

## 配置说明

### 1. 智能体配置 (config.py)

```python
# 交易引擎配置
TRADING_ENGINE_CONFIG = {
    "agents": {
        # 数据收集器配置
        "collector": {
            "enabled": True,
            "websocket_url": "wss://ws-live-data.polymarket.com",
            "clob_websocket_url": "wss://ws-subscriptions-clob.polymarket.com",
            "reconnect_interval": 5,  # 重连间隔(秒)
            "heartbeat_interval": 30,  # 心跳间隔(秒)
        },

        # 信号分析器配置
        "analyzer": {
            "enabled": True,
            "use_llm": True,
            "llm_model": "claude-3-sonnet",
            "confidence_threshold": 0.6,
            "checks": {
                "risk": {
                    "max_daily_loss": 0.02,  # 2%
                    "max_weekly_loss": 0.04,  # 4%
                    "max_single_position": 0.25,  # 25%
                    "max_total_exposure": 0.80,  # 80%
                },
                "market": {
                    "min_liquidity": 10000,  # $10,000
                    "max_spread_percent": 0.02,  # 2%
                    "dead_zone_low": 0.40,  # $0.40
                    "dead_zone_high": 0.60,  # $0.60
                }
            }
        },

        # 订单执行器配置
        "executor": {
            "enabled": True,
            "exchange_adapter": "polymarket",
            "order_timeout": 30,  # 订单超时(秒)
            "max_slippage_percent": 0.01,  # 最大滑点1%
            "execution_mode": "paper",  # "paper" or "live"
        },

        # 持仓跟踪器配置
        "position_tracker": {
            "enabled": True,
            "monitor_interval": 5,  # 监控间隔(秒)
            "exit_conditions": {
                "stop_loss": True,
                "take_profit": True,
                "trailing_stop": {
                    "enabled": True,
                    "activation_profit_pct": 0.05,  # 盈利5%激活
                    "trailing_pct": 0.03,  # 回撤3%触发
                },
                "max_hold_time": 14400,  # 最大持仓4小时(秒)
            }
        },

        # 每日审查器配置
        "reviewer": {
            "enabled": True,
            "schedule": "0 0 * * *",  # 每天UTC 00:00
            "limits": {
                "daily_loss_limit": 0.02,  # 2%
                "weekly_loss_limit": 0.04,  # 4%
                "max_drawdown_limit": 0.10,  # 10%
            },
            "actions": {
                "kill_switch": True,  # 触发熔断
                "notify": True,  # 发送通知
                "generate_report": True,  # 生成报告
            }
        }
    }
}
```

### 2. 事件订阅配置

```python
# 事件订阅映射
EVENT_SUBSCRIPTIONS = {
    # 数据收集器发布的事件
    "collector": {
        "publishes": [
            "MARKET_DATA_UPDATE",
            "PRICE_TICK",
            "ORDER_BOOK_UPDATE",
            "TRADE_UPDATE",
        ],
        "subscribes": [],  # 主动推送，不订阅
    },

    # 信号分析器订阅和发布
    "analyzer": {
        "subscribes": [
            "SIGNAL_GENERATED",  # 策略生成的信号
            "MARKET_DATA_UPDATE",  # 用于上下文
        ],
        "publishes": [
            "SIGNAL_ANALYZED",
            "SIGNAL_APPROVED",
            "SIGNAL_REJECTED",
        ],
    },

    # 订单执行器
    "executor": {
        "subscribes": [
            "SIGNAL_APPROVED",
        ],
        "publishes": [
            "ORDER_CREATED",
            "ORDER_SUBMITTED",
            "ORDER_FILLED",
            "ORDER_PARTIALLY_FILLED",
            "ORDER_REJECTED",
            "ORDER_CANCELLED",
        ],
    },

    # 持仓跟踪器
    "position_tracker": {
        "subscribes": [
            "ORDER_FILLED",
            "POSITION_OPENED",
            "PRICE_TICK",  # 用于监控价格变化
        ],
        "publishes": [
            "POSITION_UPDATED",
            "POSITION_CLOSED",
            "STOP_LOSS_TRIGGERED",
            "TAKE_PROFIT_TRIGGERED",
            "TRAILING_STOP_TRIGGERED",
        ],
    },

    # 风险管理器
    "risk_manager": {
        "subscribes": [
            "POSITION_UPDATED",
            "DAILY_REPORT",
            "WEEKLY_REPORT",
        ],
        "publishes": [
            "RISK_LIMIT_EXCEEDED",
            "DAILY_LOSS_LIMIT_HIT",
            "WEEKLY_LOSS_LIMIT_HIT",
            "KILL_SWITCH_TRIGGERED",
        ],
    },

    # 每日审查器
    "reviewer": {
        "subscribes": [
            "DAILY_SCHEDULE",  # 定时触发
        ],
        "publishes": [
            "DAILY_REPORT",
            "KILL_SWITCH_TRIGGERED",
        ],
    },
}
```

### 3. 启动配置

```python
# main.py 中的智能体启动顺序

async def start_trading_engine():
    """启动交易引擎，按依赖顺序启动各智能体。"""

    # 1. 创建事件总线
    event_bus = EventBus()

    # 2. 创建并启动数据收集器
    collector = DataCollector(event_bus)
    await collector.start()

    # 3. 创建并启动信号分析器
    analyzer = SignalAnalyzer(
        event_bus,
        llm_client=ClaudeClient(),
        config=config.ANALYZER_CONFIG
    )
    await analyzer.start()

    # 4. 创建并启动订单执行器
    executor = OrderExecutor(
        event_bus,
        exchange_adapter=PolymarketAdapter(),
        config=config.EXECUTOR_CONFIG
    )
    await executor.start()

    # 5. 创建并启动持仓跟踪器
    position_tracker = PositionTracker(
        event_bus,
        config=config.POSITION_TRACKER_CONFIG
    )
    await position_tracker.start()

    # 6. 创建并启动每日审查器
    reviewer = DailyReviewer(
        event_bus,
        config=config.REVIEWER_CONFIG
    )
    await reviewer.start()

    return {
        "event_bus": event_bus,
        "collector": collector,
        "analyzer": analyzer,
        "executor": executor,
        "position_tracker": position_tracker,
        "reviewer": reviewer,
    }
```

## 总结

多智能体协作架构通过以下方式实现：

1. **事件驱动**：所有智能体通过EventBus进行通信，不直接调用
2. **松耦合**：每个智能体只关心自己订阅的事件类型
3. **可扩展**：新增智能体只需订阅相关事件即可
4. **容错性**：单个智能体故障不会影响其他智能体运行
