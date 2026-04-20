"""
策略引擎配置
基于 polymarket-agent 的最佳实践
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from decimal import Decimal


@dataclass
class StopLossConfig:
    """止损配置 - 基于价格区间的动态阈值"""
    # 固定止损配置 (10档，基于入场价格)
    fixed_thresholds: List[Dict] = field(default_factory=lambda: [
        {"min": 0.00, "max": 0.20, "threshold": -0.30},  # 极低价：-30%
        {"min": 0.20, "max": 0.40, "threshold": -0.25},  # 低价：-25%
        {"min": 0.40, "max": 0.60, "threshold": -0.20},  # 中低价：-20%
        {"min": 0.60, "max": 0.75, "threshold": -0.15},  # 中价：-15%
        {"min": 0.75, "max": 0.85, "threshold": -0.12},  # 中高价：-12%
        {"min": 0.85, "max": 0.90, "threshold": -0.10},  # 高价：-10%
        {"min": 0.90, "max": 0.95, "threshold": -0.05},  # 准扫尾盘：-5%
        {"min": 0.95, "max": 0.97, "threshold": -0.04},  # 扫尾盘低档：-4%
        {"min": 0.97, "max": 0.99, "threshold": -0.03},  # 扫尾盘中档：-3%
        {"min": 0.99, "max": 1.00, "threshold": -0.02},  # 扫尾盘高档：-2%
    ])

    # 移动止损配置 (5档，基于入场价格和已锁定利润)
    # 注: $0.60-$0.85 为禁止交易区间（死亡区间），已移除对应档位
    # trigger_profit: 相对于入场价的百分比利润（如 0.10 = 10%利润）
    trailing_stop_config: List[Dict] = field(default_factory=lambda: [
        {"min": 0.00, "max": 0.30, "trigger_profit": 0.25, "drawdown": 0.15, "note": "低价区:25%利润触发,15%回撤"},
        {"min": 0.30, "max": 0.60, "trigger_profit": 0.20, "drawdown": 0.12, "note": "中低价区:20%利润触发,12%回撤"},
        # $0.60-$0.85 为禁止交易区间（死亡区间），不设移动止损档位
        {"min": 0.85, "max": 0.90, "trigger_profit": 0.08, "drawdown": 0.06, "note": "高价区:8%利润触发,6%回撤"},
        {"min": 0.90, "max": 0.95, "trigger_profit": 0.05, "drawdown": 0.05, "note": "极高价区:5%利润触发,5%回撤"},
        {"min": 0.95, "max": 1.00, "trigger_profit": 0.03, "drawdown": 0.03, "note": "尾盘区:3%利润触发,3%回撤"},
    ])

    # 禁止交易区间（死亡区间）- 不在这些区间开新仓
    no_trade_zones: List[Dict] = field(default_factory=lambda: [
        {"min": 0.60, "max": 0.85, "reason": "dead_zone_high_volatility"},
    ])

    # 高价止盈阈值
    high_price_exit_threshold: float = 0.999  # 价格 >= 0.999 时触发高价止盈

    # 分层止盈配置
    partial_exit_config: List[Dict] = field(default_factory=lambda: [
        {"level": 1, "profit_level": 0.20, "exit_ratio": 0.30, "description": "+20%, 卖出30%"},
        {"level": 2, "profit_level": 0.40, "exit_ratio": 0.30, "description": "+40%, 再卖出30%"},
        {"level": 3, "profit_level": 0.60, "exit_ratio": 0.40, "description": "+60%, 卖出剩余40%"},
    ])


@dataclass
class PositionMonitorConfig:
    """持仓监控配置 - 双层检查机制"""

    # Layer 1: 实时检查配置
    realtime_check: Dict = field(default_factory=lambda: {
        "enabled": True,
        "trigger_on_price_update": True,  # 价格更新时触发
        "check_interval_ms": 100,  # 最小检查间隔（毫秒）
        "hard_stop_loss": -0.07,  # 硬止损 -7%
        "hard_take_profit": 0.10,  # 硬止盈 +10%
        "max_holding_hours": 4,  # 最大持仓时间 4小时
    })

    # Layer 2: 定时同步配置
    periodic_sync: Dict = field(default_factory=lambda: {
        "enabled": True,
        "sync_interval_sec": 60,  # 每 60 秒同步一次
        "chain_rpc_batch_size": 10,  # 批量查询大小
        "max_sync_delay_ms": 5000,  # 最大同步延迟容忍
        "auto_correct_drift": True,  # 自动修正持仓漂移
    })

    # WebSocket 配置
    websocket: Dict = field(default_factory=lambda: {
        "enabled": True,
        "url": "wss://ws.prd.polymarket.com",
        "reconnect_interval_ms": 5000,
        "max_reconnect_attempts": 10,
        "heartbeat_interval_ms": 30000,
        "fallback_to_http": True,  # WebSocket 失败时回退到 HTTP
        "http_fallback_interval_ms": 5000,
    })


@dataclass
class CapitalFlowConfig:
    """资金流分析配置 - 辅助决策"""

    enabled: bool = True

    # 数据收集配置
    data_collection: Dict = field(default_factory=lambda: {
        "net_flow_1m_window": 60,  # 1分钟净资金流窗口（秒）
        "unique_traders_window": 60,  # 唯一交易者统计窗口
        "price_move_5m": 300,  # 5分钟价格变动统计
        "volume_1m": 60,  # 1分钟成交量
        "update_interval_ms": 1000,  # 数据更新间隔
    })

    # 信号阈值配置
    thresholds: Dict = field(default_factory=lambda: {
        "strong_negative_flow": -2.0,  # 强负向资金流 (>2x 平均)
        "moderate_negative_flow": -1.0,  # 中等负向资金流
        "strong_positive_flow": 2.0,  # 强正向资金流
        "moderate_positive_flow": 1.0,  # 中等正向资金流
        "min_traders_threshold": 10,  # 最小交易者数量阈值
        "max_consecutive_negative": 3,  # 最大连续负向分钟数
    })

    # 辅助决策权重
    decision_weights: Dict = field(default_factory=lambda: {
        "price_based_exit": 0.7,  # 价格基础退出权重（主）
        "flow_acceleration": 0.3,  # 资金流加速权重（辅）
        "consecutive_flow_threshold": 0.25,  # 连续资金流阈值权重
        "extreme_flow_threshold": 0.35,  # 极端资金流权重
    })


@dataclass
class Settings:
    """全局配置"""

    # 环境配置
    env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # 各模块配置
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    position_monitor: PositionMonitorConfig = field(default_factory=PositionMonitorConfig)
    capital_flow: CapitalFlowConfig = field(default_factory=CapitalFlowConfig)

    # Polymarket API 配置
    polymarket: Dict = field(default_factory=lambda: {
        "api_key": "",
        "api_secret": "",
        "passphrase": "",
        "chain_id": 137,  # Polygon mainnet
        "rpc_url": "https://polygon-rpc.com",
        "use_testnet": False,
    })

    # 数据库配置
    database: Dict = field(default_factory=lambda: {
        "url": "sqlite:///data/trader.db",
        "pool_size": 10,
        "max_overflow": 20,
        "echo": False,
    })


# 全局配置实例
settings = Settings()