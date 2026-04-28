# WestGardeng AutoTrader

A modern web-based trading application with AI-powered strategy execution for decentralized prediction markets.

[![CI](https://github.com/your-org/jmwl-autotrader/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/jmwl-autotrader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **AI-Powered Trading**: LLM-driven strategy execution with real-time market analysis
- **Real-time Data**: WebSocket-powered live updates for market data and trades
- **Secure Authentication**: JWT-based auth with refresh tokens
- **Strategy Management**: Visual strategy editor with backtesting capabilities
- **Portfolio Tracking**: Real-time P&L and position tracking
- **Risk Management**: Configurable risk limits and alerts

## Tech Stack

### Backend
- **Runtime**: Node.js 20+ with TypeScript
- **Framework**: Express.js with WebSocket support
- **Database**: SQLite with better-sqlite3
- **Authentication**: JWT with bcrypt
- **Validation**: Zod schemas
- **Logging**: Pino with pretty printing

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS with Radix UI
- **State Management**: Zustand + TanStack Query
- **Charts**: Recharts
- **Routing**: React Router v6

### Infrastructure
- **CI/CD**: GitHub Actions
- **Containerization**: Docker + Docker Compose
- **Registry**: GitHub Container Registry
- **Hosting**: VPS with automated deployment
- **CDN**: Vercel (frontend)

## Quick Start

### Prerequisites

- Node.js >= 20.0.0
- pnpm >= 9.0.0
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/jmwl-autotrader.git
cd jmwl-autotrader
```

2. Run the setup script:
```bash
pnpm setup
```

Or manually:
```bash
# Install dependencies
pnpm install

# Copy environment files
cp .env.example .env

# Initialize database
pnpm db:migrate
pnpm db:seed
```

### Development

Start all services in development mode:
```bash
pnpm dev
```

Or start individually:
```bash
# Backend only
pnpm dev:backend

# Frontend only
pnpm dev:frontend
```

The services will be available at:
- Frontend: http://localhost:5173
- Backend: http://localhost:3001
- API Docs: http://localhost:3001/api/health

### Building

Build all packages:
```bash
pnpm build
```

Build specific packages:
```bash
pnpm build:backend
pnpm build:frontend
```

### Testing

Run all tests:
```bash
pnpm test
```

Run with coverage:
```bash
pnpm test:coverage
```

### Linting and Formatting

```bash
# Lint all packages
pnpm lint

# Fix linting issues
pnpm lint:fix

# Type check
pnpm typecheck

# Format code
pnpm format

# Check formatting
pnpm format:check
```

## Docker Deployment

### Using Docker Compose

1. Build and start all services:
```bash
pnpm docker:up
```

2. View logs:
```bash
docker-compose logs -f
```

3. Stop services:
```bash
pnpm docker:down
```

### Production Deployment

The application uses GitHub Actions for CI/CD:

1. **CI Pipeline**: Runs on every PR and push to main
   - Linting and type checking
   - Unit and integration tests
   - Security audits
   - Build verification

2. **Deploy Pipeline**: Runs on releases
   - Build Docker images
   - Push to GitHub Container Registry
   - Deploy to staging/production
   - Update Sentry releases

### Manual Deployment

To deploy manually to a VPS:

1. SSH into the server:
```bash
ssh user@your-server.com
```

2. Pull latest changes:
```bash
cd /opt/jmwl-autotrader
git pull origin main
```

3. Update and restart:
```bash
docker-compose pull
docker-compose up -d --remove-orphans
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client (Browser)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   React UI   │  │  Zustand     │  │  TanStack    │          │
│  │   (Vite)     │  │  Store       │  │  Query       │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼─────────────────┼─────────────────┼──────────────────┘
          │                 │                 │
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                    ┌───────┴───────┐
                    │   Nginx       │
                    │   (Proxy)     │
                    └───────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Backend       │ │   Backend       │ │   Backend       │
│   API (3001)    │ │   WebSocket     │ │   Health        │
│                 │ │   (ws)          │ │   Check         │
│  ┌───────────┐  │ │                 │ │                 │
│  │  Express  │  │ │  ┌───────────┐  │ │  ┌───────────┐  │
│  │  Routes   │  │ │  │  Socket   │  │ │  │  Health   │  │
│  └───────────┘  │ │  │  Server   │  │ │  │  Monitor  │  │
│  ┌───────────┐  │ │  └───────────┘  │ │  └───────────┘  │
│  │  SQLite   │  │ │                 │ │                 │
│  │  (better- │  │ └─────────────────┘ └─────────────────┘
│  │  sqlite3) │  │
│  └───────────┘  │
│  ┌───────────┐  │
│  │   JWT     │  │
│  │   Auth    │  │
│  └───────────┘  │
└─────────────────┘
```

## Strategy Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Data Sources                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Gamma API (REST)      │ Market list, title, endDate, initial price         │
│  ws-live-data (WS)     │ Real-time price, order book, trade activity        │
│  sports-api.ws (WS)    │ Live scores, goals, red cards, game phase          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PolymarketDataSource                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  PriceMonitor          │ WebSocket price cache (best_bid, best_ask, spread) │
│  ActivityAnalyzer      │ Trade flow analysis (volume, netflow, whales)      │
│  RealtimeService       │ WS client forwarding trades → ActivityAnalyzer     │
│  SportsMarketMonitor   │ Score cache for ALL markets (not just positions)   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    StrategyRunner._execute_strategy()                         │
│                    (main loop polled by strategy interval)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Step 1: Fetch Gamma open market list                                         │
│  Step 2: Push market metadata to data source (endDate → hours_to_expiry)      │
│  Step 3: Sync on-chain positions                                              │
│  Step 4: For each market:                                                     │
│    ├─ Tier 1: Activity Pre-Filter (PRIMARY GATE)                              │
│    │     └── unique_traders >= 3 OR abs(netflow) >= 100                       │
│    │     └── Dead/cold markets skipped before price fetch                     │
│    ├─ Tier 2: SignalFilter (price range, dead zone, expiry, keywords)         │
│    ├─ Tier 3: EntryConditionValidator (liquidity >= 1000, orderbook depth)    │
│    ├─ Tier 4: TriggerChecker                                                  │
│    │     ├── AND logic: price_change% >= threshold AND activity_netflow >= tier│
│    │     └── OR Sports override: strong game events bypass the gate           │
│    ├─ Tier 5: BuyStrategy.evaluate()                                          │
│    │     ├── 6-factor scoring:                                                │
│    │     │    odds_bias, time_decay, orderbook_pressure, capital_flow,        │
│    │     │    information_edge, sports_momentum                               │
│    │     └── Composite score vs thresholds                                    │
│    ├─ Tier 6: AI Analysis (LLM with market data + factor scores)              │
│    │     └── Returns: action / side / confidence / stop_loss / take_profit    │
│    └─ Tier 7: Order placement (py-clob-client on-chain)                       │
│  Step 5: Position monitoring (dynamic stop-loss via sports scores + flow)     │
└─────────────────────────────────────────────────────────────────────────────┘

### Filter Logic Details

| Tier | Component | Purpose | Reject Criteria |
|------|-----------|---------|-----------------|
| 1 | Activity Pre-Filter | Eliminate dead markets early | `traders < 3` AND `\|netflow\| < 100` |
| 2 | SignalFilter | Basic market properties | Price outside range, in dead zone, expired, keyword match |
| 3 | EntryConditionValidator | Liquidity & depth check | `liquidity < 1000` or `orderbook_depth < 500` |
| 4 | TriggerChecker | Multi-factor confirmation | Neither price nor activity triggered (unless sports strong) |
| 5 | BuyStrategy | Quantitative scoring | Composite score below `buy_threshold` (0.65) |
| 6 | AI Decision | LLM discretion | Action != "buy" or confidence too low |

### Data Source Integration

| Source | Used In | Metric |
|--------|---------|--------|
| Activity (RealtimeService) | Tier 1, 4, 5 | `unique_traders`, `netflow`, `volume`, `whale_count` |
| PriceMonitor (WebSocket) | Tier 2, 3, 4, 5 | `yes_price`, `best_bid`, `best_ask`, `spread` |
| SportsMonitor | Tier 4 (override), 5 | `score_diff`, `game_status`, `time_remaining` |
| Gamma API | Tier 2 | `endDate` → `hours_to_expiry`, `question` (keywords) |

## API Documentation

### Health Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Basic health check |
| GET | `/api/health/detailed` | Detailed health with DB status |

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/register` | User registration |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/logout` | User logout |

### Strategy Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/strategies` | List all strategies |
| POST | `/api/strategies` | Create new strategy |
| GET | `/api/strategies/:id` | Get strategy by ID |
| PUT | `/api/strategies/:id` | Update strategy |
| DELETE | `/api/strategies/:id` | Delete strategy |

Full API documentation is available at `/api/docs` when running the backend server.

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Code style changes
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `test:` - Tests
- `chore:` - Build process / tooling

## License

[MIT](LICENSE) © WestGardeng Trading Systems

## Support

For support, please open an issue in the GitHub repository or contact the development team.

---

**Note**: This is a sophisticated trading system. Use with caution and never trade with funds you cannot afford to lose.
