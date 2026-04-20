"""
PolymarketClient 使用示例

展示如何使用 PolymarketClient 进行：
1. 连接和断开
2. 市场数据获取
3. 订单管理
4. 账户管理
5. 价格查询
"""

import asyncio
import os
from polymarket import PolymarketClient, PolymarketConfig, OrderSide, OrderStatus

# 从环境变量加载配置
# 注意：生产环境请勿将密钥硬编码
API_KEY = os.getenv("POLYMARKET_API_KEY", "your_api_key")
API_SECRET = os.getenv("POLYMARKET_API_SECRET", "your_api_secret")
PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE", "your_passphrase")
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "0x...")

# 代理配置（默认使用 http://127.0.0.1:7890）
# 可以通过环境变量 HTTP_PROXY 覆盖


async def example_connect():
    """示例：连接和断开"""
    print("\n=== 示例：连接和断开 ===")

    config = PolymarketConfig(
        api_key=API_KEY,
        api_secret=API_SECRET,
        passphrase=PASSPHRASE,
        private_key=PRIVATE_KEY,
        chain_id=137,  # Polygon mainnet
        rpc_url="https://polygon-rpc.com",
        host="https://clob.polymarket.com",
        use_testnet=False,
    )

    client = PolymarketClient(config)

    # 连接
    connected = await client.connect()
    print(f"连接状态: {connected}")

    # 获取统计信息
    stats = client.get_stats()
    print(f"统计信息: {stats}")

    # 健康检查
    health = await client.health_check()
    print(f"健康状态: {health}")

    # 断开连接
    await client.disconnect()
    print("已断开连接")


async def example_market_data(client: PolymarketClient):
    """示例：市场数据获取"""
    print("\n=== 示例：市场数据获取 ===")

    # 获取市场列表
    markets = await client.get_markets(active_only=True, limit=10)
    print(f"获取到 {len(markets)} 个活跃市场")

    if markets:
        # 显示第一个市场的基本信息
        first_market = markets[0]
        print(f"\n第一个市场信息:")
        print(f"  市场ID: {first_market.get('market_id')}")
        print(f"  问题: {first_market.get('question')}")
        print(f"  代币ID: {first_market.get('token_id')}")

        # 获取订单簿
        token_id = first_market.get('token_id')
        if token_id:
            order_book = await client.get_order_book(token_id)
            print(f"\n订单簿信息:")
            print(f"  买一档: {order_book.get('bids', [])[0] if order_book.get('bids') else '无'}")
            print(f"  卖一档: {order_book.get('asks', [])[0] if order_book.get('asks') else '无'}")

            # 获取当前价格
            price = await client.get_price(token_id)
            print(f"  当前价格(中间价): {price}")


async def example_order_management(client: PolymarketClient):
    """示例：订单管理"""
    print("\n=== 示例：订单管理 ===")

    # 获取当前持仓
    positions = await client.get_positions()
    print(f"当前持仓数量: {len(positions)}")

    # 获取未成交订单
    open_orders = await client.get_open_orders()
    print(f"未成交订单数量: {len(open_orders)}")

    # 获取交易历史
    trades = await client.get_trade_history(limit=10)
    print(f"最近交易数量: {len(trades)}")

    # 示例：创建订单（注意：这会在真实环境创建真实订单）
    # token_id = "your_token_id"
    # order = await client.place_order(
    #     token_id=token_id,
    #     side="BUY",  # 或 "SELL"
    #     price=0.55,
    #     size=100.0,
    #     order_type="limit"
    # )
    # print(f"创建订单成功: {order.order_id}")

    # 示例：查询订单状态
    # order_id = "your_order_id"
    # order_status = await client.get_order_status(order_id)
    # if order_status:
    #     print(f"订单状态: {order_status.status}")

    # 示例：取消订单
    # success = await client.cancel_order(order_id)
    # print(f"取消订单: {'成功' if success else '失败'}")


async def example_account_management(client: PolymarketClient):
    """示例：账户管理"""
    print("\n=== 示例：账户管理 ===")

    # 获取账户余额
    balance = await client.get_balance()
    print(f"账户余额信息:")
    print(f"  可用现金: {balance.get('cash', 0)}")
    print(f"  持仓市值: {balance.get('portfolio_value', 0)}")
    print(f"  总资产: {balance.get('total_value', 0)}")
    print(f"  币种: {balance.get('currency', 'USDC')}")

    # 获取持仓
    positions = await client.get_positions()
    print(f"\n当前持仓:")
    for pos in positions:
        print(f"  Token: {pos.token_id}")
        print(f"    方向: {pos.side.value}")
        print(f"    数量: {pos.size}")
        print(f"    平均入场价: {pos.avg_entry_price}")
        print(f"    未实现盈亏: {pos.unrealized_pnl}")


async def main():
    """主函数"""
    print("PolymarketClient 使用示例")
    print("=" * 50)

    # 配置
    config = PolymarketConfig(
        api_key=API_KEY,
        api_secret=API_SECRET,
        passphrase=PASSPHRASE,
        private_key=PRIVATE_KEY,
        chain_id=137,
        rpc_url="https://polygon-rpc.com",
        host="https://clob.polymarket.com",
        use_testnet=False,
    )

    # 创建客户端
    client = PolymarketClient(config)

    try:
        # 连接
        connected = await client.connect()
        if not connected:
            print("连接失败，请检查配置")
            return

        # 运行示例
        await example_market_data(client)
        await example_account_management(client)
        await example_order_management(client)

        # 统计信息
        print("\n=== 统计信息 ===")
        stats = client.get_stats()
        print(f"API调用次数: {stats['api_calls']}")
        print(f"错误次数: {stats['errors']}")
        print(f"连接时间: {stats['connection_time']}")

    except Exception as e:
        print(f"错误: {e}")
    finally:
        # 断开连接
        await client.disconnect()
        print("\n示例完成")


if __name__ == "__main__":
    asyncio.run(main())
