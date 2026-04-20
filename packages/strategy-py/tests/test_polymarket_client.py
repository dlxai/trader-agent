"""
PolymarketClient 测试

测试所有 API 方法的实现和返回格式。
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

# 导入被测试的模块
from polymarket.client import (
    PolymarketClient,
    PolymarketConfig,
    OrderResult,
    OrderStatus,
    OrderSide,
    Position,
    Trade,
)


# ==================== Fixtures ====================

@pytest.fixture
def mock_config():
    """Mock 配置"""
    return PolymarketConfig(
        api_key="test_api_key",
        api_secret="test_api_secret",
        passphrase="test_passphrase",
        private_key="0x" + "a" * 64,
        chain_id=137,
        rpc_url="https://polygon-rpc.com",
        host="https://clob.polymarket.com",
        use_testnet=False,
    )


@pytest.fixture
def mock_clob_client():
    """Mock ClobClient"""
    mock = MagicMock()
    return mock


@pytest.fixture
def client(mock_config, mock_clob_client):
    """创建测试客户端"""
    with patch("polymarket.client.ClobClient", return_value=mock_clob_client):
        client = PolymarketClient(mock_config)
        return client


# ==================== 连接测试 ====================

@pytest.mark.asyncio
async def test_connect_success(client, mock_clob_client):
    """测试成功连接"""
    # 配置 mock
    mock_clob_client.set_api_creds = MagicMock()

    # 执行
    result = await client.connect()

    # 验证
    assert result is True
    assert client.connected is True
    assert client._connection_time is not None
    mock_clob_client.set_api_creds.assert_called_once()


@pytest.mark.asyncio
async def test_connect_failure(client, mock_clob_client):
    """测试连接失败"""
    # 配置 mock 抛出异常
    mock_clob_client.set_api_creds = MagicMock(side_effect=Exception("Connection failed"))

    # 执行
    result = await client.connect()

    # 验证
    assert result is False
    assert client.connected is False


@pytest.mark.asyncio
async def test_disconnect(client):
    """测试断开连接"""
    # 先连接
    client._connected = True
    client._connection_time = datetime.now()

    # 断开
    await client.disconnect()

    # 验证
    assert client.connected is False
    assert client._client is None


# ==================== 市场数据测试 ====================

@pytest.mark.asyncio
async def test_get_markets(client, mock_clob_client):
    """测试获取市场列表"""
    # 配置 mock
    mock_clob_client.get_markets = MagicMock(return_value={
        "markets": [
            {"id": "market1", "question": "Test 1"},
            {"id": "market2", "question": "Test 2"},
        ]
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_markets()

    # 验证
    assert len(result) == 2
    assert result[0]["id"] == "market1"
    mock_clob_client.get_markets.assert_called_once()


@pytest.mark.asyncio
async def test_get_order_book(client, mock_clob_client):
    """测试获取订单簿"""
    # 配置 mock
    mock_clob_client.get_order_book = MagicMock(return_value={
        "token_id": "token123",
        "bids": [{"price": 0.55, "size": 100.0}],
        "asks": [{"price": 0.56, "size": 150.0}],
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_order_book("token123")

    # 验证
    assert result["token_id"] == "token123"
    assert len(result["bids"]) == 1
    assert len(result["asks"]) == 1
    mock_clob_client.get_order_book.assert_called_once_with("token123", depth=100)


@pytest.mark.asyncio
async def test_get_market_condition(client, mock_clob_client):
    """测试获取市场条件"""
    # 配置 mock
    mock_clob_client.get_condition = MagicMock(return_value={
        "condition_id": "cond123",
        "status": "active",
        "outcomes": [{"id": "out1", "name": "Yes"}, {"id": "out2", "name": "No"}],
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_market_condition("cond123")

    # 验证
    assert result["condition_id"] == "cond123"
    assert result["status"] == "active"
    mock_clob_client.get_condition.assert_called_once_with("cond123")


# ==================== 订单管理测试 ====================

@pytest.mark.asyncio
async def test_create_order(client, mock_clob_client):
    """测试创建订单"""
    # 配置 mock
    mock_clob_client.create_order = MagicMock(return_value={
        "order_id": "order123",
        "status": "open",
        "side": "BUY",
        "price": 0.55,
        "size": 100.0,
        "filled_size": 0.0,
        "created_at": datetime.now().isoformat(),
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.create_order(
        token_id="token123",
        side="BUY",
        price=0.55,
        size=100.0,
        order_type="limit",
    )

    # 验证
    assert result.order_id == "order123"
    assert result.status == OrderStatus.OPEN
    assert result.side == OrderSide.BUY
    assert result.price == 0.55
    assert result.size == 100.0


@pytest.mark.asyncio
async def test_cancel_order(client, mock_clob_client):
    """测试取消订单"""
    # 配置 mock
    mock_clob_client.cancel = MagicMock(return_value={"success": True})

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.cancel_order("order123")

    # 验证
    assert result is True
    mock_clob_client.cancel.assert_called_once_with("order123")


@pytest.mark.asyncio
async def test_get_order(client, mock_clob_client):
    """测试获取订单信息"""
    # 配置 mock
    mock_clob_client.get_order = MagicMock(return_value={
        "id": "order123",
        "status": "filled",
        "side": "BUY",
        "price": 0.55,
        "original_size": 100.0,
        "size_matched": 100.0,
        "created_at": datetime.now().isoformat(),
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_order("order123")

    # 验证
    assert result is not None
    assert result.order_id == "order123"
    assert result.status == OrderStatus.FILLED
    assert result.filled_size == 100.0


@pytest.mark.asyncio
async def test_get_open_orders(client, mock_clob_client):
    """测试获取未成交订单"""
    # 配置 mock
    mock_clob_client.get_open_orders = MagicMock(return_value=[
        {
            "id": "order1",
            "status": "open",
            "side": "BUY",
            "price": 0.55,
            "original_size": 100.0,
            "market_id": "market1",
        },
        {
            "id": "order2",
            "status": "open",
            "side": "SELL",
            "price": 0.60,
            "original_size": 50.0,
            "market_id": "market1",
        },
    ])

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_open_orders()

    # 验证
    assert len(result) == 2
    assert result[0].order_id == "order1"
    assert result[1].order_id == "order2"


# ==================== 账户管理测试 ====================

@pytest.mark.asyncio
async def test_get_balance(client, mock_clob_client):
    """测试获取账户余额"""
    # 配置 mock
    mock_clob_client.get_balance = MagicMock(return_value={
        "cash": 10000.0,
        "portfolio_value": 5000.0,
        "total_value": 15000.0,
        "currency": "USDC",
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_balance()

    # 验证
    assert result["cash"] == 10000.0
    assert result["portfolio_value"] == 5000.0
    assert result["total_value"] == 15000.0


@pytest.mark.asyncio
async def test_get_positions(client, mock_clob_client):
    """测试获取持仓"""
    # 配置 mock
    mock_clob_client.get_positions = MagicMock(return_value=[
        {
            "token_id": "token1",
            "market_id": "market1",
            "side": "BUY",
            "size": 100.0,
            "avg_entry_price": 0.55,
            "unrealized_pnl": 10.0,
            "realized_pnl": 0.0,
        },
        {
            "token_id": "token2",
            "market_id": "market2",
            "side": "SELL",
            "size": 50.0,
            "avg_entry_price": 0.60,
            "unrealized_pnl": -5.0,
            "realized_pnl": 2.0,
        },
    ])

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_positions()

    # 验证
    assert len(result) == 2
    assert result[0].token_id == "token1"
    assert result[0].side == OrderSide.BUY
    assert result[1].token_id == "token2"
    assert result[1].side == OrderSide.SELL


@pytest.mark.asyncio
async def test_get_trade_history(client, mock_clob_client):
    """测试获取交易历史"""
    # 配置 mock
    mock_clob_client.get_trades = MagicMock(return_value=[
        {
            "trade_id": "trade1",
            "order_id": "order1",
            "token_id": "token1",
            "side": "BUY",
            "price": 0.55,
            "size": 100.0,
            "fee": 0.1,
            "timestamp": datetime.now().isoformat(),
        },
        {
            "trade_id": "trade2",
            "order_id": "order2",
            "token_id": "token1",
            "side": "SELL",
            "price": 0.60,
            "size": 50.0,
            "fee": 0.05,
            "timestamp": datetime.now().isoformat(),
        },
    ])

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.get_trade_history(limit=10)

    # 验证
    assert len(result) == 2
    assert result[0].trade_id == "trade1"
    assert result[0].side == OrderSide.BUY
    assert result[1].trade_id == "trade2"
    assert result[1].side == OrderSide.SELL
    mock_clob_client.get_trades.assert_called_once_with(limit=10, offset=0)


# ==================== 统计和工具测试 ====================

@pytest.mark.asyncio
async def test_get_stats(client):
    """测试获取统计信息"""
    # 先连接并设置一些统计
    client._connected = True
    client._connection_time = datetime.now()
    client._api_calls = 100
    client._errors = 5
    client._retries = 10

    # 执行
    result = client.get_stats()

    # 验证
    assert result["connected"] is True
    assert result["connection_time"] is not None
    assert result["api_calls"] == 100
    assert result["errors"] == 5
    assert result["retries"] == 10


@pytest.mark.asyncio
async def test_health_check(client, mock_clob_client):
    """测试健康检查"""
    # 配置 mock
    mock_clob_client.get_balance = MagicMock(return_value={
        "cash": 10000.0,
        "portfolio_value": 5000.0,
        "total_value": 15000.0,
    })

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.health_check()

    # 验证
    assert result["status"] == "healthy"
    assert result["connected"] is True
    assert result["balance"] == 10000.0
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_health_check_unhealthy(client, mock_clob_client):
    """测试健康检查失败"""
    # 配置 mock 抛出异常
    mock_clob_client.get_balance = MagicMock(side_effect=Exception("API Error"))

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行
    result = await client.health_check()

    # 验证
    assert result["status"] == "unhealthy"
    assert result["connected"] is True
    assert "error" in result
    assert "timestamp" in result


# ==================== 重试机制测试 ====================

@pytest.mark.asyncio
async def test_retry_mechanism(client, mock_clob_client):
    """测试重试机制"""
    # 配置 mock，前两次调用失败，第三次成功
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception(f"Temporary error {call_count}")
        return {"markets": []}

    mock_clob_client.get_markets = MagicMock(side_effect=side_effect)

    # 先连接
    client._connected = True
    client._client = mock_clob_client

    # 执行 - 应该重试并最终成功
    result = await client.get_markets()

    # 验证
    assert result == []
    assert call_count == 3  # 重试了 3 次


# ==================== 辅助方法测试 ====================

@pytest.mark.asyncio
async def test_parse_order_result(client):
    """测试订单结果解析"""
    raw_data = {
        "order_id": "order123",
        "status": "filled",
        "side": "BUY",
        "price": 0.55,
        "size": 100.0,
        "filled_size": 100.0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    result = client._parse_order_result(raw_data, "BUY", 0.55, 100.0)

    assert isinstance(result, OrderResult)
    assert result.order_id == "order123"
    assert result.status == OrderStatus.FILLED
    assert result.side == OrderSide.BUY
    assert result.price == 0.55
    assert result.size == 100.0
    assert result.filled_size == 100.0
    assert result.remaining_size == 0.0
    assert result.created_at is not None
    assert result.updated_at is not None
    assert result.raw_data == raw_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
