# Python 统一后端设计方案

**日期**: 2025-01-20
**状态**: 已批准，待实施
**方案**: B (完全统一)

---

## 1. 设计目标

将割裂的 TypeScript 后端 (@jmwl/backend + @pmt/engine) 统一为单一的 Python FastAPI 后端，同时：

- 保持前端兼容性 (API 路径、WebSocket、认证格式)
- 整合 strategy-py 的完整策略能力
- 支持 PostgreSQL (生产) 和 SQLite (本地/测试)
- 保留交易引擎架构: Collector→Analyzer→Executor→Reviewer

---

## 2. 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Python Unified Backend                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI Application                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │   │
│  │  │  REST API   │  │  WebSocket  │  │      Dependency Injection│ │   │
│  │  │   Routers   │  │  Endpoints  │  │      (Services Layer)   │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────┼─────────────────────────────────────┐   │
│  │                    Business Logic Layer                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │   │
│  │  │   Auth      │  │  Portfolio  │  │   Trading   │  │ Strategy │ │   │
│  │  │  Service    │  │  Service    │  │  Service    │  │ Service  │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────┼─────────────────────────────────────┐   │
│  │                      Trading Engine                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │   │
│  │  │  Collector  │→ │  Analyzer   │→ │  Executor   │→ │ Reviewer │ │   │
│  │  │  (WS/REST)  │  │  (LLM)      │  │  (Orders)   │  │ (Daily)  │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌───────────────────────────┼─────────────────────────────────────┐   │
│  │                    Data Layer                                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │   │
│  │  │ SQLAlchemy  │  │   Alembic   │  │   Redis (Optional)      │ │   │
│  │  │   2.0 ORM   │  │  Migrations │  │   Cache / Queue         │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 技术栈

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | **FastAPI** | 0.110+ | 异步原生、自动 OpenAPI、WebSocket |
| ORM | **SQLAlchemy 2.0** | 2.0+ | 统一支持 PostgreSQL/SQLite |
| 迁移 | **Alembic** | 最新 | SQLAlchemy 官方迁移工具 |
| 认证 | **fastapi-users** 或自研 | - | JWT + OAuth2 |
| 配置 | **Pydantic Settings** | v2 | 环境变量统一管理 |
| 任务队列 | **Celery + Redis** | - | 后台任务（Reviewer 定时任务）|
| 测试 | **pytest + httpx** | - | 异步测试支持 |
| 类型检查 | **mypy** | - | 严格类型检查 |

---

## 4. 项目结构

```
packages/backend-py/                    # 新的 Python 统一后端
├── pyproject.toml                      # Poetry 配置
├── README.md
├── alembic/                            # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── src/
│   ├── __init__.py
│   ├── main.py                         # FastAPI 应用入口
│   ├── config.py                       # Pydantic Settings 配置
│   ├── database.py                     # SQLAlchemy 引擎和会话
│   ├── dependencies.py                 # FastAPI 依赖注入
│   │
│   ├── models/                         # SQLAlchemy ORM 模型
│   │   ├── __init__.py
│   │   ├── base.py                     # 基础模型类
│   │   ├── user.py                     # 用户模型
│   │   ├── portfolio.py                # 投资组合
│   │   ├── position.py                 # 持仓
│   │   ├── order.py                    # 订单
│   │   ├── strategy.py                 # 策略配置
│   │   ├── signal_log.py               # 信号日志
│   │   └── market_data.py              # 市场数据缓存
│   │
│   ├── schemas/                        # Pydantic 模型 (Request/Response)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── user.py
│   │   ├── auth.py
│   │   ├── portfolio.py
│   │   ├── position.py
│   │   ├── order.py
│   │   ├── trade.py
│   │   └── websocket.py
│   │
│   ├── routers/                        # FastAPI 路由
│   │   ├── __init__.py
│   │   ├── auth.py                     # 认证 (登录/注册/刷新)
│   │   ├── users.py                    # 用户管理
│   │   ├── portfolios.py               # 投资组合
│   │   ├── positions.py                # 持仓
│   │   ├── orders.py                   # 订单
│   │   ├── strategies.py               # 策略
│   │   ├── trades.py                   # 交易执行
│   │   ├── health.py                   # 健康检查
│   │   └── websocket.py                # WebSocket 端点
│   │
│   ├── services/                       # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py             # 认证逻辑
│   │   ├── user_service.py             # 用户管理
│   │   ├── portfolio_service.py        # 投资组合
│   │   ├── trading_service.py          # 交易服务
│   │   ├── websocket_manager.py        # WebSocket 连接管理
│   │   └── market_data_service.py      # 市场数据服务
│   │
│   ├── trading_engine/                 # 交易引擎 (Python 重写)
│   │   ├── __init__.py
│   │   ├── base.py                     # 基础类和接口
│   │   ├── collector.py                # 数据收集器 (WebSocket/REST)
│   │   ├── analyzer.py                 # 信号分析器 (集成 LLM)
│   │   ├── executor.py                 # 订单执行器
│   │   ├── reviewer.py                 # 绩效复盘器
│   │   ├── risk_manager.py             # 风险管理
│   │   ├── event_bus.py                # 事件总线
│   │   ├── models/                     # 引擎内部模型
│   │   └── strategies/                 # 策略实现
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── buy_strategy.py         # 买入策略
│   │       └── capital_flow.py         # 资金流策略
│   │
│   ├── core/                           # 核心工具
│   │   ├── __init__.py
│   │   ├── security.py                 # 密码哈希、JWT
│   │   ├── exceptions.py               # 自定义异常
│   │   ├── logging.py                  # 日志配置
│   │   └── validators.py               # 自定义验证器
│   │
│   └── tasks/                          # 后台任务 (Celery)
│       ├── __init__.py
│       ├── celery_app.py               # Celery 应用配置
│       ├── reviewer_task.py            # 每日复盘任务
│       └── coordinator_task.py         # 定时协调任务
│
├── tests/                              # 测试
│   ├── unit/
│   ├── integration/
│   ├── conftest.py                     # pytest 配置
│   └── fixtures/
│
├── alembic.ini                         # Alembic 配置
├── pytest.ini                          # pytest 配置
├── .env.example                        # 环境变量示例
└── Dockerfile                          # 容器化
```

---

## 5. 关键设计决策

### 5.1 认证系统

选择 **fastapi-users** 库，它提供：
- 完整的用户管理（注册、登录、密码重置）
- JWT 策略支持
- OAuth2 集成（可选）
- 与 SQLAlchemy 集成

### 5.2 数据库访问模式

使用 **Repository 模式**：

```python
# repositories/portfolio.py
class PortfolioRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(self, user_id: UUID) -> List[Portfolio]:
        ...

    async def create(self, data: PortfolioCreate) -> Portfolio:
        ...
```

### 5.3 交易引擎事件驱动架构

```python
# 事件总线示例
class EventBus:
    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable):
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event):
        for handler in self._handlers.get(event.type, []):
            await handler(event)

# 使用
bus = EventBus()

# Collector 发布信号
bus.publish(TriggerEvent(market_id="...", signal_data={...}))

# Analyzer 订阅并处理
bus.subscribe(EventType.TRIGGER, analyzer.handle_trigger)
```

### 5.4 与前端兼容性

完全保持现有 API 契约：

| 端点 | Node.js | Python FastAPI |
|------|---------|----------------|
| 登录 | POST /api/auth/login | POST /api/auth/login |
| 获取投资组合 | GET /api/portfolios | GET /api/portfolios |
| WebSocket | ws://localhost:3001/ws | ws://localhost:3001/ws |

Response 结构完全一致：
```json
{
  "success": true,
  "data": { ... },
  "meta": { "timestamp": "...", "requestId": "..." }
}
```

---

## 6. 开发阶段规划

### Phase 1: 基础架构 (Week 1)
- [ ] 项目骨架搭建 ( Poetry + FastAPI )
- [ ] 数据库模型 (SQLAlchemy)
- [ ] Alembic 迁移
- [ ] 认证系统 (fastapi-users)
- [ ] 基础 API (health, auth)

### Phase 2: 核心 API (Week 2)
- [ ] Portfolio API
- [ ] Position API
- [ ] Order API
- [ ] Strategy API
- [ ] WebSocket 基础连接

### Phase 3: 交易引擎 (Week 3-4)
- [ ] Event Bus 实现
- [ ] Collector (数据收集)
- [ ] Analyzer (LLM 集成)
- [ ] Executor (订单执行)
- [ ] Reviewer (每日复盘)
- [ ] Risk Manager (风险管理)

### Phase 4: 集成测试 (Week 5)
- [ ] 前端对接测试
- [ ] 性能测试
- [ ] 安全审计
- [ ] 部署文档

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 开发周期过长 | 高 | 分 Phase 交付，每个 Phase 可独立使用 |
| 与前端不兼容 | 中 | 早期建立 API 契约测试，确保 Response 格式一致 |
| 性能不如 Node.js | 低 | FastAPI 异步性能优秀，提前做压力测试 |
| 数据库迁移失败 | 中 | Alembic 分步迁移，保留原数据备份 |

---

## 8. 决策记录 (ADR)

### ADR-001: Python 统一后端
- **状态**: 已批准
- **决策**: 使用 Python FastAPI 完全替换 Node.js 后端
- **原因**:
  - strategy-py 已有完整策略实现，TypeScript engine 需要重复开发
  - Python 量化生态更丰富
  - 统一技术栈降低维护成本
- **替代方案**: 保留 Node.js + Python 混合（被拒绝，维护成本高）

### ADR-002: FastAPI 框架
- **状态**: 已批准
- **决策**: 使用 FastAPI 而非 Flask/Django
- **原因**:
  - 原生异步支持（交易场景需要高并发）
  - 自动 OpenAPI 文档
  - Pydantic v2 类型安全
- **替代方案**: Flask（异步支持弱）、Django（过重）

### ADR-003: 数据库策略
- **状态**: 已批准
- **决策**: SQLAlchemy 2.0 + 混合数据库（SQLite 本地/PostgreSQL 生产）
- **原因**:
  - 开发阶段 SQLite 零配置
  - 生产环境 PostgreSQL 更可靠
  - SQLAlchemy 抽象层统一接口
- **替代方案**: 只用 PostgreSQL（开发成本高）、只用 SQLite（生产不可靠）

---

## 9. 结论

本设计文档批准了 **Python FastAPI 统一后端** 的架构方案，关键决策包括：

1. **完全统一** (方案 B): 废弃 Node.js 后端，全部用 Python 重写
2. **技术栈**: FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL/SQLite
3. **架构**: 保留 Collector→Analyzer→Executor→Reviewer 流程，用 Python 实现
4. **兼容**: 保持前端 API 契约不变，无缝切换

下一步: 使用 `writing-plans` skill 制定详细的实施计划。

---

**批准人**:
**日期**: 2025-01-20
**版本**: 1.0
