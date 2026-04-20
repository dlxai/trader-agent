# OrderManager 设计文档

## 概述

`OrderManager` 是一个完整的订单生命周期管理模块，为 Polymarket 交易策略提供订单创建、取消、查询和状态跟踪功能。

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                     OrderManager                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ OrderStateManager│ │ OrderEventEmitter│ │ PolymarketClient│ │
│  │ (状态管理)       │ │ (事件系统)        │ │ (API 客户端)    │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 1. OrderManager

主类，负责协调所有订单操作。

**主要职责：**
- 订单创建和提交
- 订单取消
- 订单查询
- 事件管理

**核心方法：**

| 方法 | 描述 | 返回类型 |
|------|------|----------|
| `create_order()` | 创建并提交订单 | `OrderResult` |
| `cancel_order()` | 取消指定订单 | `CancelResult` |
| `cancel_all_orders()` | 取消所有未成交订单 | `List[CancelResult]` |
| `get_order()` | 获取订单详情 | `Optional[Order]` |
| `get_open_orders()` | 获取未成交订单列表 | `List[Order]` |
| `get_order_history()` | 获取订单历史 | `List[Order]` |
| `get_order_statistics()` | 获取订单统计 | `Dict[str, Any]` |
| `update_order_from_fill()` | 更新订单成交状态 | `None` |

### 2. OrderStateManager

管理内存中的订单状态，提供快速的订单查询和状态更新。

**数据结构：**
```python
{
    "_orders": Dict[str, Order],           # 订单ID -> 订单
    "_open_orders": Set[str],               # 未成交订单ID集合
    "_token_orders": Dict[str, Set[str]], # Token -> 订单ID映射
    "_order_history": List[str],            # 订单历史（按时间）
}
```

### 3. OrderEventEmitter

事件发布/订阅系统，支持订单状态变更的事件通知。

**事件类型：**

| 事件类型 | 描述 | 数据字段 |
|----------|------|----------|
| `order_created` | 订单创建成功 | order_id, token_id, side, price, size |
| `order_status_changed` | 订单状态变更 | order_id, old_status, new_status |
| `order_filled` | 订单部分成交 | order_id, fill_size, fill_price, total_filled |
| `order_completed` | 订单完全成交 | order_id, average_fill_price |
| `order_cancelled` | 订单取消 | order_id, cancelled_at |
| `order_rejected` | 订单被拒绝 | order_id, error_message |

## 数据模型

### Order (订单)

```python
@dataclass
class Order:
    id: str                          # 订单ID
    token_id: str                    # Token/Market ID
    side: str                        # BUY 或 SELL
    price: float                     # 订单价格
    size: float                      # 订单数量
    filled_size: float               # 已成交数量
    remaining_size: float            # 剩余数量
    order_type: str                  # limit 或 market
    time_in_force: str               # GTC, IOC, FOK
    status: str                      # PENDING, OPEN, FILLED, ...
    created_at: datetime             # 创建时间
    updated_at: datetime             # 更新时间
    filled_at: Optional[datetime]    # 成交时间
    cancelled_at: Optional[datetime]  # 取消时间
    average_fill_price: Optional[float]  # 平均成交价格
    metadata: Dict                     # 额外元数据
```

### 订单状态流转

```
                    ┌─────────────┐
                    │   PENDING   │
                    │   (等待)    │
                    └──────┬──────┘
                           │ 提交到交易所
                           ▼
                    ┌─────────────┐
         ┌─────────▶│    OPEN     │
         │         │  (已提交)   │
         │         └──────┬──────┘
         │                  │
    ┌────┴────┐             │ 部分成交
    │CANCELLED│             ▼
    │ (已取消)│    ┌─────────────────┐
    └─────────┘◀───│ PARTIALLY_FILLED │
                   │    (部分成交)     │
                   └────────┬────────┘
                            │ 继续成交
                            ▼
                     ┌─────────────┐
         ┌───────────│   FILLED    │
         │           │   (已成交)   │
         │           └─────────────┘
         │
    ┌────┴────┐  ┌──────────┐  ┌─────────┐
    │ EXPIRED │  │ REJECTED │  │  ERROR  │
    │ (过期)  │  │ (被拒绝)  │  │ (错误)   │
    └─────────┘  └──────────┘  └─────────┘
```

## 使用示例

### 基础使用

```python
import asyncio
from polymarket.client import PolymarketClient, PolymarketConfig
from polymarket.order_manager import OrderManager

async def main():
    # 1. 创建客户端并连接
    config = PolymarketConfig(
        api_key="your_api_key",
        api_secret="your_api_secret",
        passphrase="your_passphrase",
        private_key="your_private_key"
    )

    client = PolymarketClient(config)
    await client.connect()

    # 2. 创建 OrderManager
    order_manager = OrderManager(
        client=client,
        max_retries=3,
        retry_delay=1.0
    )

    # 3. 初始化
    await order_manager.initialize()

    # 4. 创建订单
    result = await order_manager.create_order(
        token_id="123456789",
        side="BUY",
        price=0.65,
        size=100.0,
        order_type="limit",
        time_in_force="GTC"
    )

    if result.success:
        print(f"订单创建成功: {result.order.id}")

        # 5. 查询订单
        order = order_manager.get_order(result.order.id)
        print(f"订单状态: {order.status}")

        # 6. 取消订单
        cancel_result = await order_manager.cancel_order(result.order.id)
        if cancel_result.success:
            print("订单取消成功")
    else:
        print(f"订单创建失败: {result.error_message}")

    # 7. 关闭
    await order_manager.shutdown()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### 事件监听示例

```python
def on_order_filled(event):
    data = event['data']
    print(f"订单 {data['order_id']} 部分成交")
    print(f"  成交数量: {data['fill_size']}")
    print(f"  成交价格: {data['fill_price']}")
    print(f"  总成交: {data['total_filled']}/{data['total_filled'] + data['remaining']}")

# 注册监听器
order_manager.on("order_filled", on_order_filled)
```

### 批量操作示例

```python
# 取消所有未成交订单
results = await order_manager.cancel_all_orders()
print(f"取消结果: {sum(1 for r in results if r.success)}/{len(results)} 成功")

# 获取特定 Token 的订单
token_orders = order_manager.get_open_orders(token_id="123456")
print(f"Token 123456 的未成交订单: {len(token_orders)}")
```

## 实现的功能列表

### 已完成的功能

1. **订单创建**
   - 支持限价单 (limit) 和市价单 (market)
   - 支持多种 Time In Force 类型 (GTC, IOC, FOK)
   - 完整的参数验证
   - 异步创建和提交
   - 错误处理和重试机制

2. **订单取消**
   - 单订单取消
   - 批量取消所有未成交订单
   - 按 Token 过滤取消
   - 取消状态跟踪

3. **订单查询**
   - 根据订单 ID 查询
   - 查询所有未成交订单
   - 按 Token 过滤查询
   - 订单历史查询（支持时间范围和分页）
   - 订单统计信息

4. **状态管理**
   - 完整的订单状态流转
   - 内存中的订单缓存
   - 按 Token 索引订单
   - 订单历史记录

5. **事件系统**
   - 订单创建事件
   - 订单状态变更事件
   - 订单成交事件
   - 订单完成事件
   - 订单取消事件
   - 支持事件订阅和取消订阅

6. **成交处理**
   - 实时成交更新
   - 自动计算平均成交价格
   - 部分成交跟踪
   - 完全成交检测

7. **错误处理**
   - 完整的异常捕获
   - 错误代码和消息
   - 重试机制
   - 日志记录

8. **统计功能**
   - 总订单统计
   - 按状态分类统计
   - 按 Token 分类统计
   - 成交量统计

## 主要设计决策

### 1. 分层架构

采用三层架构：
- **OrderManager**: 对外接口层，处理业务逻辑
- **OrderStateManager**: 状态管理层，管理订单缓存
- **OrderEventEmitter**: 事件层，处理事件通知

这种分层使得：
- 职责清晰，易于测试
- 可以独立替换各层实现
- 便于扩展和维护

### 2. 异步设计

全面使用 `async/await`：
- 所有 I/O 操作都是异步的
- 支持并发处理多个订单
- 避免阻塞事件循环

```python
async def create_order(...):
    # 异步提交订单
    order_response = await self._submit_order_to_api(order)
    # ...
```

### 3. 状态机模式

订单状态使用严格的状态流转：
- `PENDING` → `OPEN` → (`FILLED` | `PARTIALLY_FILLED` | `CANCELLED` | `EXPIRED` | `REJECTED`)
- 每个状态变更都会触发事件

好处：
- 明确的状态边界
- 易于跟踪订单生命周期
- 防止非法状态转换

### 4. 事件驱动

采用发布-订阅模式：
- 组件间通过事件通信
- 松耦合设计
- 易于添加新的事件处理器

```python
# 订阅事件
order_manager.on("order_filled", on_order_filled)

# 发布事件
self._event_emitter.emit("order_filled", {...})
```

### 5. 内存缓存

订单数据存储在内存中：
- 快速查询（O(1)）
- 支持按订单ID、Token、状态等多维度索引
- 定期同步到持久化存储（可选）

权衡：
- 优点：极快的查询速度
- 缺点：程序重启数据丢失（可以通过持久化解决）

### 6. 错误处理和重试

全面的错误处理策略：
- 分层错误捕获
- 自动重试机制
- 指数退避算法
- 详细的错误日志

```python
async def _retry_with_backoff(self, operation, *args, **kwargs):
    for attempt in range(self._max_retries):
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            # 指数退避
            delay = self._retry_delay * (2 ** attempt)
            await asyncio.sleep(delay)
```

### 7. 类型安全

全面使用 Python 类型注解：
- 编译时类型检查（使用 mypy）
- IDE 智能提示
- 更好的文档

## 订单状态流转图

```
                    ┌─────────────┐
                    │   PENDING   │
                    │   (等待)    │
                    └──────┬──────┘
                           │ 提交到交易所
                           ▼
                    ┌─────────────┐
         ┌─────────▶│    OPEN     │
         │         │  (已提交)   │
         │         └──────┬──────┘
         │                  │
    ┌────┴────┐             │ 部分成交
    │CANCELLED│             ▼
    │ (已取消)│    ┌─────────────────┐
    └─────────┘◀───│ PARTIALLY_FILLED │
                   │    (部分成交)     │
                   └────────┬────────┘
                            │ 继续成交
                            ▼
                     ┌─────────────┐
         ┌───────────│   FILLED    │
         │           │   (已成交)   │
         │           └─────────────┘
         │
    ┌────┴────┐  ┌──────────┐  ┌─────────┐
    │ EXPIRED │  │ REJECTED │  │  ERROR  │
    │ (过期)  │  │ (被拒绝)  │  │ (错误)   │
    └─────────┘  └──────────┘  └─────────┘
```

### 状态说明

| 状态 | 说明 | 可转移状态 |
|------|------|-----------|
| PENDING | 订单已创建，等待提交到交易所 | OPEN, ERROR, REJECTED |
| OPEN | 订单已提交到交易所，等待成交 | PARTIALLY_FILLED, FILLED, CANCELLED, EXPIRED |
| PARTIALLY_FILLED | 订单部分成交 | FILLED, CANCELLED, OPEN |
| FILLED | 订单完全成交 | - (终态) |
| CANCELLED | 订单已取消 | - (终态) |
| EXPIRED | 订单已过期 | - (终态) |
| REJECTED | 订单被拒绝 | - (终态) |
| ERROR | 订单处理出错 | - (终态) |

## API 集成

### py-clob-client-v2 集成

`OrderManager` 通过 `PolymarketClient` 与 `py-clob-client-v2` 库交互：

```python
# 获取底层 CLOB 客户端
clob_client = None
if hasattr(self._client, '_clob_client'):
    clob_client = self._client._clob_client

# 调用 CLOB API 创建订单
# response = await clob_client.create_order(...)
```

### 错误处理

API 调用使用指数退避重试机制：

```python
async def _retry_with_backoff(self, operation, *args, **kwargs):
    for attempt in range(self._max_retries):
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            if attempt < self._max_retries - 1:
                delay = self._retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
    raise last_exception
```

## 性能考虑

### 1. 内存使用

- 订单数据存储在内存中，适用于中等规模的订单量（< 10,000 订单）
- 如需支持更大规模，可考虑：
  - 使用 Redis 等外部缓存
  - 定期持久化到数据库
  - 分页加载历史订单

### 2. 并发处理

- 使用 `asyncio.Lock` 保护状态更新
- 支持并发创建多个订单
- WebSocket 连接共享

### 3. 查询优化

- 使用多个索引（订单ID、Token、状态）
- O(1) 订单查询
- 高效的范围查询（时间范围）

## 测试

### 单元测试

```bash
# 运行测试
cd packages/strategy-py
python -m pytest tests/test_order_manager.py -v
```

### 测试覆盖

- 订单状态管理（StateManager）
- 事件系统（EventEmitter）
- 订单数据模型（Order dataclass）
- 参数验证
- 统计功能

## 部署建议

### 1. 生产环境配置

```python
order_manager = OrderManager(
    client=client,
    max_retries=5,          # 生产环境更多重试
    retry_delay=2.0,          # 更长的重试间隔
    enable_websocket=True     # 启用 WebSocket 实时更新
)
```

### 2. 监控和告警

- 监控订单状态统计
- 设置错误率告警
- 监控 API 调用延迟

### 3. 日志记录

- 所有操作记录 INFO 级别日志
- 错误记录 ERROR 级别日志
- 调试信息记录 DEBUG 级别日志

## 未来扩展

### 1. 计划功能

- [ ] WebSocket 实时订单更新
- [ ] 订单持久化存储
- [ ] 批量订单操作
- [ ] 高级订单类型（条件单、止损单）
- [ ] 订单风险管理

### 2. 优化方向

- 使用 Redis 缓存订单数据
- 实现分布式锁（多实例部署）
- 添加订单执行分析
- 优化 WebSocket 重连机制

## 参考资料

- [py-clob-client-v2](https://github.com/Polymarket/py-clob-client-v2) - Polymarket Python 客户端
- [Polymarket API 文档](https://docs.polymarket.com/)
- [Python asyncio 文档](https://docs.python.org/3/library/asyncio.html)
