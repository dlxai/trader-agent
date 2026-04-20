"""
多Agent系统使用示例

演示如何初始化和协调多个Agent
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入Agent组件
from agents.core.agent_base import AgentConfig
from agents.core.message_bus import MessageBus
from agents.core.registry import AgentRegistry, AgentMetadata
from agents.agents.strategy_agent import StrategyAgent, StrategyConfig
from agents.agents.execution_agent import ExecutionAgent, ExecutionConfig
from agents.agents.risk_agent import RiskAgent, RiskConfig
from agents.agents.analytics_agent import AnalyticsAgent, AnalyticsConfig
from agents.agents.orchestrator_agent import OrchestratorAgent, OrchestratorConfig
from agents.protocol.constants import AgentType, SignalType, OrderSide
from agents.protocol.messages import MarketData, TradingSignal, OrderIntent


class MultiAgentSystem:
    """多Agent系统"""

    def __init__(self):
        self.orchestrator: Optional[OrchestratorAgent] = None
        self.message_bus: Optional[MessageBus] = None
        self.registry: Optional[AgentRegistry] = None
        self.running = False

    async def initialize(self):
        """初始化系统"""
        logger.info("Initializing Multi-Agent System...")

        # 1. 初始化消息总线
        self.message_bus = MessageBus()
        await self.message_bus.start()
        logger.info("MessageBus started")

        # 2. 初始化注册表
        self.registry = AgentRegistry()
        logger.info("AgentRegistry initialized")

        # 3. 创建编排Agent
        orchestrator_config = OrchestratorConfig(
            agent_id="orchestrator_001",
            agent_name="main_orchestrator",
            heartbeat_interval=30.0
        )
        self.orchestrator = OrchestratorAgent(orchestrator_config)

        # 注册编排Agent自己
        self.registry.register(
            AgentMetadata(
                agent_id=self.orchestrator.agent_id,
                agent_type=AgentType.ORCHESTRATOR,
                agent_name="main_orchestrator",
                capabilities=["coordination", "monitoring", "management"]
            ),
            self.orchestrator
        )

        # 4. 创建并注册其他Agent
        await self._create_and_register_agents()

        # 5. 初始化编排Agent
        await self.orchestrator.initialize()

        logger.info("Multi-Agent System initialized successfully")

    async def _create_and_register_agents(self):
        """创建并注册所有Agent"""

        # 1. 创建策略Agent
        strategy_config = StrategyConfig(
            agent_id="strategy_001",
            agent_name="main_strategy",
            min_confidence_threshold=0.7,
            max_signals_per_minute=5
        )
        strategy_agent = StrategyAgent(strategy_config)

        self.registry.register(
            AgentMetadata(
                agent_id=strategy_agent.agent_id,
                agent_type=AgentType.STRATEGY,
                agent_name="main_strategy",
                capabilities=["signal_generation", "market_analysis", "decision_making"]
            ),
            strategy_agent
        )
        self.orchestrator.register_agent(strategy_agent, AgentType.STRATEGY)
        logger.info(f"Registered StrategyAgent: {strategy_agent.agent_id}")

        # 2. 创建执行Agent
        execution_config = ExecutionConfig(
            agent_id="execution_001",
            agent_name="main_execution",
            max_concurrent_orders=5,
            enable_order_splitting=True
        )
        execution_agent = ExecutionAgent(execution_config)

        self.registry.register(
            AgentMetadata(
                agent_id=execution_agent.agent_id,
                agent_type=AgentType.EXECUTION,
                agent_name="main_execution",
                capabilities=["order_execution", "order_management", "execution_optimization"]
            ),
            execution_agent
        )
        self.orchestrator.register_agent(execution_agent, AgentType.EXECUTION)
        logger.info(f"Registered ExecutionAgent: {execution_agent.agent_id}")

        # 3. 创建风控Agent
        risk_config = RiskConfig(
            agent_id="risk_001",
            agent_name="main_risk",
            max_daily_loss=-0.05,
            max_drawdown=-0.10,
            auto_close_on_stop_loss=True
        )
        risk_agent = RiskAgent(risk_config)

        self.registry.register(
            AgentMetadata(
                agent_id=risk_agent.agent_id,
                agent_type=AgentType.RISK,
                agent_name="main_risk",
                capabilities=["risk_monitoring", "risk_intervention", "compliance_checking"]
            ),
            risk_agent
        )
        self.orchestrator.register_agent(risk_agent, AgentType.RISK)
        logger.info(f"Registered RiskAgent: {risk_agent.agent_id}")

        # 4. 创建分析Agent
        analytics_config = AnalyticsConfig(
            agent_id="analytics_001",
            agent_name="main_analytics",
            max_concurrent_analyses=2,
            enable_persistent_storage=False
        )
        analytics_agent = AnalyticsAgent(analytics_config)

        self.registry.register(
            AgentMetadata(
                agent_id=analytics_agent.agent_id,
                agent_type=AgentType.ANALYTICS,
                agent_name="main_analytics",
                capabilities=["backtesting", "performance_analysis", "optimization", "reporting"]
            ),
            analytics_agent
        )
        self.orchestrator.register_agent(analytics_agent, AgentType.ANALYTICS)
        logger.info(f"Registered AnalyticsAgent: {analytics_agent.agent_id}")

    async def start(self):
        """启动系统"""
        if self.running:
            logger.warning("System is already running")
            return

        logger.info("Starting Multi-Agent System...")
        self.running = True

        # 启动编排Agent（它会启动其他Agent）
        await self.orchestrator.start()

        logger.info("Multi-Agent System started successfully")

    async def stop(self):
        """停止系统"""
        if not self.running:
            return

        logger.info("Stopping Multi-Agent System...")
        self.running = False

        # 停止编排Agent（它会停止其他Agent）
        if self.orchestrator:
            await self.orchestrator.stop()

        # 停止消息总线
        if self.message_bus:
            await self.message_bus.stop()

        logger.info("Multi-Agent System stopped")

    async def simulate_market_data(self):
        """模拟市场数据"""
        """模拟市场数据发送"""
        tokens = ["BTC-USD", "ETH-USD"]

        while self.running:
            try:
                for token in tokens:
                    import random
                    price = 50000 + random.uniform(-1000, 1000) if "BTC" in token else 3000 + random.uniform(-100, 100)

                    market_data = MarketData(
                        msg_id=str(uuid.uuid4()),
                        msg_type="market_data",
                        sender="simulator",
                        token_id=token,
                        price=price,
                        bid=price * 0.999,
                        ask=price * 1.001,
                        timestamp=datetime.utcnow()
                    )

                    if self.message_bus:
                        await self.message_bus.publish(market_data)

                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in market data simulation: {e}")
                await asyncio.sleep(5)


async def main():
    """主函数"""
    # 创建多Agent系统
    system = MultiAgentSystem()

    try:
        # 初始化系统
        await system.initialize()

        # 启动系统
        await system.start()

        # 启动市场数据模拟
        asyncio.create_task(system.simulate_market_data())

        # 运行一段时间
        logger.info("System is running. Press Ctrl+C to stop.")
        while system.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received stop signal")

    finally:
        # 停止系统
        await system.stop()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
