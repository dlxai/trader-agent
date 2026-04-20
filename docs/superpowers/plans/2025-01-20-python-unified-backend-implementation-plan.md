# Python 统一后端实施计划

**日期**: 2025-01-20
**状态**: 已批准
**设计文档**: [2025-01-20-python-unified-backend-design.md](../specs/2025-01-20-python-unified-backend-design.md)

---

## 1. 项目结构

```
packages/backend-py/
├── pyproject.toml              # Poetry 配置
├── poetry.lock                 # 锁定依赖版本
├── README.md                   # 项目说明
├── .env.example                # 环境变量示例
├── alembic.ini                 # Alembic 配置
├── pytest.ini                  # pytest 配置
├── Makefile                    # 常用命令快捷方式
│
├── alembic/                    # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── src/
│   ├── __init__.py
│   ├── __version__.py          # 版本信息
│   │
│   ├── main.py                 # FastAPI 应用入口
│   ├── config.py               # Pydantic Settings 配置
│   ├── database.py             # SQLAlchemy 引擎和会话
│   ├── dependencies.py         # FastAPI 依赖注入
│   │
│   ├── models/                 # SQLAlchemy ORM 模型
│   │   ├── __init__.py
│   │   ├── base.py             # 基础模型类 (Base, TimestampMixin, UUIDMixin)
│   │   ├── user.py             # User, RefreshToken
│   │   ├── portfolio.py        # Portfolio
│   │   ├── position.py         # Position
│   │   ├── order.py            # Order
│   │   ├── strategy.py         # Strategy, StrategyConfig
│   │   ├── signal.py           # SignalLog
│   │   └── market_data.py      # MarketDataCache
│   │
│   ├── schemas/                # Pydantic 模型 (Request/Response)
│   │   ├── __init__.py
│   │   ├── base.py             # 基础响应模型
│   │   ├── auth.py             # 登录/注册/Token
│   │   ├── user.py             # 用户信息
│   │   ├── portfolio.py        # 投资组合
│   │   ├── position.py         # 持仓
│   │   ├── order.py            # 订单
│   │   ├── trade.py            # 交易执行
│   │   ├── strategy.py         # 策略
│   │   └── websocket.py        # WebSocket 消息
│   │
│   ├── routers/                # FastAPI 路由
│   │   ├── __init__.py
│   │   ├── auth.py             # POST /api/auth/login, /register, /refresh
│   │   ├── users.py            # GET /api/users/me, PUT /api/users/me
│   │   ├── portfolios.py       # CRUD /api/portfolios
│   │   ├── positions.py        # GET /api/positions, /api/positions/{id}
│   │   ├── orders.py           # POST /api/orders, GET /api/orders
│   │   ├── strategies.py       # CRUD /api/strategies
│   │   ├── trades.py           # POST /api/trades/execute
│   │   ├── health.py           # GET /health, /health/deep
│   │   └── websocket.py        # WebSocket /ws
│   │
│   ├── services/               # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── portfolio_service.py
│   │   ├── trading_service.py
│   │   ├── market_data_service.py
│   │   └── websocket_manager.py  # WebSocket 连接管理
│   │
│   ├── trading_engine/         # 交易引擎 (Python 实现)
│   │   ├── __init__.py
│   │   ├── base.py             # 基础类和接口定义
│   │   ├── config.py           # 引擎配置
│   │   ├── event_bus.py        # 事件总线实现
│   │   ├── types.py            # 类型定义
│   │   │
│   │   ├── collector.py        # 数据收集器
│   │   ├── analyzer.py         # 信号分析器 (LLM 集成)
│   │   ├── executor.py         # 订单执行器
│   │   ├── reviewer.py         # 绩效复盘器
│   │   ├── risk_manager.py     # 风险管理
│   │   └── position_tracker.py # 仓位跟踪
│   │
│   ├── core/                   # 核心工具
│   │   ├── __init__.py
│   │   ├── security.py         # 密码哈希、JWT 生成/验证
│   │   ├── exceptions.py       # 自定义异常类
│   │   ├── logging.py          # 日志配置
│   │   └── validators.py       # 自定义验证器
│   │
│   └── tasks/                  # 后台任务 (Celery)
       ├── __init__.py
       ├── celery_app.py       # Celery 应用配置
       ├── reviewer_task.py    # 每日复盘任务
       └── coordinator_task.py # 定时协调任务

├── tests/                      # 测试
│   ├── __init__.py
│   ├── conftest.py             # pytest 配置和 fixtures
│   ├── unit/                   # 单元测试
│   │   ├── __init__.py
│   │   ├── test_models/
│   │   ├── test_services/
│   │   └── test_trading_engine/
│   ├── integration/            # 集成测试
│   │   ├── __init__.py
│   │   ├── test_api/
│   │   ├── test_auth/
│   │   └── test_database/
│   └── fixtures/               # 测试数据
       ├── __init__.py
       ├── users.py
       ├── portfolios.py
       └── market_data.py

├── docs/                       # 文档
│   ├── api.md                  # API 文档
│   ├── deployment.md         # 部署指南
│   └── development.md          # 开发指南
│
├── scripts/                    # 脚本
│   ├── init_db.py              # 初始化数据库
│   ├── run_migrations.py       # 运行迁移
│   └── seed_data.py            # 种子数据
│
├── Dockerfile                  # 容器化
├── docker-compose.yml          # 本地开发环境
├── .dockerignore
├── .gitignore
└── Makefile                    # 常用命令
```

---

## 3. 详细实施阶段

### Phase 1: 基础架构 (Week 1)

**目标**: 可运行的 FastAPI 骨架 + 数据库模型

#### Week 1 任务清单

| 任务 ID | 任务描述 | 预计工时 | 依赖 | 验收标准 |
|---------|----------|----------|------|----------|
| **P1-T1** | 项目初始化 (Poetry + 目录结构) | 2h | - | `poetry install` 成功 |
| **P1-T2** | 配置管理 (Pydantic Settings) | 2h | P1-T1 | `.env` 加载正常 |
| **P1-T3** | 数据库基础 (SQLAlchemy 2.0) | 4h | P1-T1 | 连接池配置完成 |
| **P1-T4** | 基础模型 (User, Portfolio) | 4h | P1-T3 | 模型可导入 |
| **P1-T5** | Alembic 迁移 | 2h | P1-T4 | `alembic upgrade head` 成功 |
| **P1-T6** | FastAPI 骨架 | 4h | P1-T2 | `uvicorn src.main:app --reload` 运行 |
| **P1-T7** | Health Check API | 1h | P1-T6 | GET /health 返回 200 |
| **P1-T8** | 日志配置 | 2h | P1-T6 | 日志输出格式正确 |

**Week 1 总计**: ~27 小时 (约 3.5 工作日)

#### Week 1 详细实现

**P1-T1: 项目初始化**

```bash
# 执行命令
mkdir -p packages/backend-py
cd packages/backend-py

# 初始化 Poetry
poetry init --name jmwl-backend --description "JMWL Trading Backend (Python)" --author "Your Name <email@example.com>" --python "^3.11" --no-interaction

# 添加依赖
poetry add fastapi uvicorn[standard] sqlalchemy alembic pydantic-settings
poetry add asyncpg psycopg2-binary aiosqlite
poetry add python-jose[cryptography] passlib[bcrypt] python-multipart python-dotenv
poetry add websockets

# 添加开发依赖
poetry add --group dev pytest pytest-asyncio httpx mypy black isort ruff

# 创建目录结构
mkdir -p src/{models,schemas,routers,services,trading_engine,core,tasks}
mkdir -p tests/{unit,integration,fixtures}
mkdir -p alembic/versions
mkdir -p scripts
```

**P1-T2: 配置管理**

已在设计文档中提供完整代码，见 `src/config.py`。

**P1-T3: 数据库基础**

创建 `src/database.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

from src.config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,  # 调试模式下输出 SQL
    pool_pre_ping=True,   # 连接前 ping 测试
    poolclass=NullPool if settings.DATABASE_TYPE == "sqlite" else None,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 基础模型类
Base = declarative_base()


async def get_async_session() -> AsyncSession:
    """依赖注入用的异步会话生成器"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库（创建所有表）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
```

**P1-T4: 基础模型**

见设计文档中的模型定义。关键模型：
- `User` - 用户
- `Portfolio` - 投资组合
- `Position` - 持仓
- `Order` - 订单
- `Strategy` - 策略

**P1-T5: Alembic 迁移**

```bash
# 初始化 Alembic
alembic init alembic

# 修改 alembic/env.py 使用异步引擎
# 修改 alembic.ini 配置

# 生成初始迁移
alembic revision --autogenerate -m "initial"

# 执行迁移
alembic upgrade head
```

**P1-T6: FastAPI 骨架**

创建 `src/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.database import init_db, close_db
from src.core.logging import setup_logging
from src.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    setup_logging()
    await init_db()
    yield
    # 关闭
    await close_db()


def create_application() -> FastAPI:
    """应用工厂函数"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="JMWL Trading Backend API (Python)",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(health.router, prefix="/health", tags=["health"])
    # TODO: 注册其他路由

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
    )
```

**P1-T7: Health Check API**

创建 `src/routers/health.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.schemas.base import HealthResponse, ApiResponse

router = APIRouter()


@router.get("", response_model=ApiResponse[HealthResponse])
async def health_check():
    """基础健康检查"""
    return ApiResponse(
        success=True,
        data=HealthResponse(
            status="healthy",
            version="0.1.0",
            service="jmwl-backend-py"
        )
    )


@router.get("/deep", response_model=ApiResponse[HealthResponse])
async def deep_health_check(session: AsyncSession = Depends(get_async_session)):
    """深度健康检查（包含数据库连接）"""
    # 测试数据库连接
    try:
        from sqlalchemy import text
        result = await session.execute(text("SELECT 1"))
        await result.scalar()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return ApiResponse(
        success=True,
        data=HealthResponse(
            status="healthy" if db_status == "connected" else "degraded",
            version="0.1.0",
            service="jmwl-backend-py",
            database=db_status
        )
    )
```

**P1-T8: 日志配置**

创建 `src/core/logging.py`:

```python
import logging
import sys
from pathlib import Path

from src.config import settings


def setup_logging():
    """配置日志系统"""

    # 日志格式
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 配置根日志器
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # 减少第三方库的日志噪音
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING if not settings.DEBUG else logging.INFO)

    # 创建日志目录（如果需要文件日志）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("jmwl")
    logger.info(f"Logging configured (DEBUG={settings.DEBUG})")
```

---

## 2. 快速开始指南

### 环境准备

```bash
# 1. 进入项目目录
cd packages/backend-py

# 2. 安装 Poetry (如果未安装)
curl -sSL https://install.python-poetry.org | python3 -

# 3. 安装依赖
poetry install

# 4. 复制环境变量
cp .env.example .env
# 编辑 .env 设置必要配置

# 5. 运行数据库迁移
poetry run alembic upgrade head

# 6. 启动开发服务器
poetry run uvicorn src.main:app --reload --port 3001
```

### 验证安装

```bash
# 健康检查
curl http://localhost:3001/health

# 预期输出
{"success":true,"data":{"status":"healthy","version":"0.1.0","service":"jmwl-backend-py"}}
```

---

## 3. 下一步

本计划已完成 Phase 1 的详细设计。Phase 2-5 将在后续迭代中展开，每个 Phase 开始前会更新本文档。

**立即开始**: Phase 1 实施
