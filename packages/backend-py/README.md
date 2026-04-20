# JMWL Trading Backend (Python)

Python unified backend for JMWL Trading Platform.

## Overview

This is a complete rewrite of the TypeScript Node.js backend in Python, using:

- **FastAPI** - Modern, fast web framework
- **SQLAlchemy 2.0** - SQL toolkit and ORM
- **Pydantic** - Data validation
- **Alembic** - Database migrations
- **Poetry** - Dependency management

## Project Structure

```
packages/backend-py/
├── src/
│   ├── main.py              # FastAPI application entry
│   ├── config.py            # Settings management
│   ├── database.py          # Database configuration
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── routers/             # API endpoints
│   ├── services/            # Business logic
│   ├── trading_engine/      # Trading engine
│   ├── core/                # Utilities
│   └── tasks/               # Background tasks
├── tests/                   # Test suite
├── alembic/                 # Database migrations
└── pyproject.toml           # Project configuration
```

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- PostgreSQL (optional, SQLite works for development)

### Installation

```bash
# 1. Navigate to project directory
cd packages/backend-py

# 2. Install dependencies
poetry install

# 3. Copy environment variables
cp .env.example .env

# 4. Edit .env with your settings
# Especially: JWT_SECRET, DATABASE_URL

# 5. Run database migrations
poetry run alembic upgrade head

# 6. Start development server
poetry run uvicorn src.main:app --reload --port 3001
```

### Verify Installation

```bash
# Health check
curl http://localhost:3001/health

# Expected response:
# {"success":true,"data":{"status":"healthy","version":"0.1.0",...}}
```

## Development

### Useful Commands

```bash
# Run development server
poetry run uvicorn src.main:app --reload --port 3001

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=src --cov-report=term-missing

# Run linting
poetry run black src tests
poetry run isort src tests
poetry run ruff check src tests

# Run type checking
poetry run mypy src

# Database migrations
poetry run alembic revision --autogenerate -m "description"
poetry run alembic upgrade head
poetry run alembic downgrade -1
```

### Project Conventions

1. **Models**: SQLAlchemy 2.0 style with type hints
2. **Schemas**: Pydantic v2 models
3. **Routers**: FastAPI router instances
4. **Services**: Business logic layer
5. **Dependencies**: Use FastAPI dependency injection

### Code Style

- **Formatter**: Black (line length 100)
- **Import Sorting**: isort (black profile)
- **Linter**: Ruff
- **Type Checker**: mypy (strict mode)

## Architecture

### Request Flow

```
HTTP Request
    ↓
FastAPI Router
    ↓
Dependency Injection (DB Session, Current User)
    ↓
Service Layer (Business Logic)
    ↓
SQLAlchemy ORM
    ↓
Database (PostgreSQL/SQLite)
```

### Trading Engine Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           TRADING ENGINE COMPLETE FLOW                               │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 1. MARKET DATA COLLECTION                                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌─────────────────────────────────────────────────────────┐
│  RTDS WebSocket │     │  Activity Stream (wss://ws-live-data.polymarket.com)    │
│  (Primary)      │────▶│  - trade_id, market_id, price, size, timestamp           │
└─────────────────┘     └─────────────────────────────────────────────────────────┘
         │
         │              ┌─────────────────────────────────────────────────────────┐
         │              │  CLOB WebSocket                                         │
         └─────────────▶│  (wss://ws-subscriptions-clob.polymarket.com)         │
                        │  - Order book updates, Price ticks, Best bid/ask         │
                        └─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 2. DATA COLLECTOR → EVENT BUS                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────────────────┐
│ Data Sources │───▶│  Collector   │───▶│        EVENT BUS (Pub/Sub)               │
└──────────────┘    └──────────────┘    └──────────────────────────────────────────┘
                                               │
        ┌──────────────────────────────────────┼──────────────────────────────────────┐
        │                                      │                                      │
        ▼                                      ▼                                      ▼
┌───────────────────┐            ┌───────────────────┐            ┌───────────────────┐
│ MARKET_DATA_UPDATE│            │ ORDER_BOOK_UPDATE │            │   TRADE_UPDATE    │
└───────────────────┘            └───────────────────┘            └───────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 3. SIGNAL ANALYSIS (5-Layer Screening + LLM)                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│ SIGNAL_GENERATED │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          5-LAYER SIGNAL SCREENING                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
│ Layer 1: Risk      │   │ Layer 2: Portfolio │   │ Layer 3: Market    │
│ Check              │   │ Check                │   │ Check              │
├────────────────────┤   ├────────────────────┤   ├────────────────────┤
│ • Daily loss limit │   │ • Available balance  │   │ • Liquidity > $10k │
│ • Position size    │   │ • Max positions      │   │ • Spread < 2%      │
│ • Max exposure     │   │ • Trading mode       │   │ • Dead zone check  │
│ • Stop loss valid  │   │ • Existing position  │   │ • Volatility       │
│ • Risk amount      │   │                      │   │                    │
└────────┬───────────┘   └────────┬───────────┘   └────────┬───────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                │
                                ▼
┌────────────────────┐   ┌────────────────────┐   ┌────────────────────┐
│ Layer 4: Odds Edge │   │ Layer 5: Technical │   │ LLM Deep Analysis  │
│ Check              │   │ Check              │   │ (Claude/GPT)       │
├────────────────────┤   ├────────────────────┤   ├────────────────────┤
│ • Edge >= 5%       │   │ • Support/Resistance│   │ • Market context   │
│ • Implied prob     │   │ • Trend alignment  │   │ • Risk assessment  │
│ • Real prob est.   │   │ • Volume spike     │   │ • Verdict:         │
│                    │   │ • Pattern          │   │   APPROVE/REJECT   │
└────────────────────┘   └────────────────────┘   │ /MODIFY            │
                                                  └────────────────────┘

┌───────────────────┐
│  ALL CHECKS PASS  │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐     ┌───────────────────┐
│  SIGNAL_APPROVED  │     │  SIGNAL_REJECTED  │
└────────┬──────────┘     └───────────────────┘
         │
         ▼
┌───────────────────┐
│   ORDER_CREATED   │
└───────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 4. ORDER EXECUTION                                                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   ORDER_CREATED   │────▶│  ORDER_SUBMITTED  │────▶│ Exchange Adapter  │
└───────────────────┘     └───────────────────┘     └─────────┬─────────┘
                                                                │
                      ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
                      │                                         │                                         │
                      ▼                                         ▼                                         ▼
            ┌───────────────────┐                     ┌───────────────────┐                     ┌───────────────────┐
            │   ORDER_FILLED    │                     │ ORDER_PARTIALLY_  │                     │   ORDER_REJECTED  │
            └─────────┬─────────┘                     │     FILLED        │                     └───────────────────┘
                      │                               └───────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 5. POSITION MONITORING (SL/TP/Trailing Stop)                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────┐     ┌───────────────────────────────────────────────────────────┐
│   ORDER_FILLED    │────▶│                 POSITION OPENED                           │
└───────────────────┘     └────────────────────┬────────────────────────────────────┘
                                                  │
                                                  ▼
                              ┌───────────────────────────────────────────────────────┐
                              │              POSITION TRACKER                         │
                              │  ┌─────────────────────────────────────────────────┐  │
                              │  │  Monitor Loop (every 5 seconds)                 │  │
                              │  │                                                 │  │
                              │  │  1. Get current market price                    │  │
                              │  │  2. Calculate unrealized P&L                    │  │
                              │  │  3. Check exit conditions:                      │  │
                              │  │     ┌─────────────────────────────────────────┐   │  │
                              │  │     │ • STOP LOSS:                          │   │  │
                              │  │     │   Long: price <= stop_loss_price      │   │  │
                              │  │     │   Short: price >= stop_loss_price     │   │  │
                              │  │     ├─────────────────────────────────────────┤   │  │
                              │  │     │ • TAKE PROFIT:                        │   │  │
                              │  │     │   Long: price >= take_profit_price    │   │  │
                              │  │     │   Short: price <= take_profit_price   │   │  │
                              │  │     ├─────────────────────────────────────────┤   │  │
                              │  │     │ • TRAILING STOP:                      │   │  │
                              │  │     │   Activate: profit_pct > 5%           │   │  │
                              │  │     │   Trigger: price <= highest * 0.97    │   │  │
                              │  │     ├─────────────────────────────────────────┤   │  │
                              │  │     │ • MAX HOLD TIME:                      │   │  │
                              │  │     │   Close after 4 hours                 │   │  │
                              │  │     └─────────────────────────────────────────┘   │  │
                              │  │  4. If triggered → submit exit order              │  │
                              │  │  5. Position closed → stop monitoring            │  │
                              │  └─────────────────────────────────────────────────┘  │
                              └───────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 6. DAILY REVIEWER                                                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────┐     ┌───────────────────────────────────────────────────────────┐
│  DAILY (UTC 0)   │────▶│                   REVIEWER                                │
└───────────────────┘     └────────────────────┬──────────────────────────────────────┘
                                               │
                                               ▼
                              ┌───────────────────────────────────────────────────────┐
                              │  1. Aggregate daily statistics                        │
                              │  2. Check risk limits (daily loss > 2% ?)              │
                              │  3. Check weekly limits (weekly loss > 4% ?)        │
                              │  4. Check max drawdown (drawdown > 10% ?)             │
                              │  5. Generate report                                  │
                              │  6. If limits exceeded → KILL SWITCH triggered       │
                              └───────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│ RISK LIMITS SUMMARY                                                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┬──────────────────────────┬──────────────────────────────┐
│ Risk Type                │ Limit                    │ Action When Exceeded         │
├──────────────────────────┼──────────────────────────┼──────────────────────────────┤
│ Daily Loss               │ -2% of portfolio         │ Halt trading for the day     │
│ Weekly Loss              │ -4% of portfolio         │ Halt trading for the week    │
│ Max Drawdown             │ -10% from peak           │ Halt all trading             │
│ Single Position          │ Max 25% of portfolio     │ Reject new orders            │
│ Total Exposure           │ Max 80% of portfolio     │ Reject new orders            │
│ Position Size            │ Per strategy config      │ Reject signal                │
└──────────────────────────┴──────────────────────────┴──────────────────────────────┘

## Architecture

### Request Flow

```
HTTP Request
    ↓
FastAPI Router
    ↓
Dependency Injection (DB Session, Current User)
    ↓
Service Layer (Business Logic)
    ↓
SQLAlchemy ORM
    ↓
Database (PostgreSQL/SQLite)
```

### Trading Engine Flow

```
Market Data (WebSocket/REST)
    ↓
Collector
    ↓
Event Bus
    ↓
Analyzer (LLM)
    ↓
Executor
    ↓
Order Placement
    ↓
Position Tracker
    ↓
Reviewer (Daily)
```

## Deployment

### Docker

```bash
# Build image
docker build -t jmwl-backend .

# Run container
docker run -p 3001:3001 --env-file .env jmwl-backend
```

### Production Checklist

- [ ] Change default `JWT_SECRET`
- [ ] Use PostgreSQL (not SQLite)
- [ ] Enable HTTPS/TLS
- [ ] Configure proper CORS origins
- [ ] Set up log aggregation
- [ ] Configure monitoring/alerting
- [ ] Run security audit
- [ ] Set up backup strategy

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [Link]
- Documentation: [Link]
- Email: [Email]
