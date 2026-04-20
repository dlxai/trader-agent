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
