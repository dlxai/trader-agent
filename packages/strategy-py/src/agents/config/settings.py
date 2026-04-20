"""
系统配置

使用Pydantic进行配置验证和管理
"""

import os
from typing import Dict, List, Optional, Any
from pydantic import BaseSettings, Field, validator
from functools import lru_cache


class AgentSystemSettings(BaseSettings):
    """
    Agent系统设置
    """
    # 系统模式
    mode: str = Field(default="autonomous", env="AGENT_MODE")
    trading_enabled: bool = Field(default=False, env="TRADING_ENABLED")

    # 消息总线
    message_bus_type: str = Field(default="memory", env="MESSAGE_BUS_TYPE")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")

    # 监控
    enable_monitoring: bool = Field(default=True, env="ENABLE_MONITORING")
    metrics_endpoint: str = Field(default="/metrics", env="METRICS_ENDPOINT")

    # 日志
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")

    # 风控
    max_daily_loss: float = Field(default=-0.05, env="MAX_DAILY_LOSS")
    max_drawdown: float = Field(default=-0.10, env="MAX_DRAWDOWN")
    max_position_size: float = Field(default=10000.0, env="MAX_POSITION_SIZE")

    # 分析
    enable_analytics: bool = Field(default=True, env="ENABLE_ANALYTICS")
    analysis_storage_path: Optional[str] = Field(default=None, env="ANALYSIS_STORAGE_PATH")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> AgentSystemSettings:
    """获取配置（缓存）"""
    return AgentSystemSettings()


def load_config(config_path: Optional[str] = None) -> AgentSystemSettings:
    """
    加载配置

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        AgentSystemSettings实例
    """
    if config_path and os.path.exists(config_path):
        # 从文件加载
        import yaml
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        return AgentSystemSettings(**config_data)

    # 从环境变量加载
    return get_settings()


# 全局配置实例
settings = get_settings()
