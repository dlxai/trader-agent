# Polymarket Trader

A standalone Electron desktop application for Polymarket trading with AI-powered analysis, risk management, and real-time market monitoring.

## Features

- **Real-time Market Data**: WebSocket-driven data collection from Polymarket
- **AI-Powered Analysis**: Three specialized AI agents (Analyzer, Reviewer, Risk Manager)
- **Multi-Provider LLM Support**: 24+ providers including OpenAI, Anthropic, Gemini, DeepSeek, and more
- **Risk Management**: Automatic circuit breakers, drawdown protection, and Kelly criterion position sizing
- **Auto-Apply Filter Proposals**: High-confidence trading parameter adjustments
- **Desktop Notifications**: Critical alerts and warnings via OS notifications
- **Chat Interface**: Interactive Hall chat with all three agents

## Architecture

Monorepo structure with 4 packages:

- `@pmt/engine` - Trading engine (collector, executor, database)
- `@pmt/llm` - LLM provider abstraction and agent runners
- `@pmt/main` - Electron main process
- `@pmt/renderer` - React UI

## Quick Start

### Prerequisites

- Node.js 24+
- pnpm 10+

### Installation

```bash
# Install dependencies
pnpm install

# Build all packages
pnpm build

# Run in development mode
pnpm dev
```

### Packaging

```bash
# Build for current platform
pnpm dist

# Build for specific platforms
pnpm dist:mac
pnpm dist:win
pnpm dist:linux
```

## Development

```bash
# Run tests
pnpm test:run

# Type check
pnpm typecheck

# Clean build artifacts
pnpm clean
```

## Configuration

The application stores data in:

- **macOS**: `~/Library/Application Support/polymarket-trader/`
- **Windows**: `%APPDATA%/polymarket-trader/`
- **Linux**: `~/.config/polymarket-trader/`

Override with `POLYMARKET_TRADER_HOME` environment variable.

## LLM Providers

Supported providers:

- **API Key**: OpenAI, Anthropic, DeepSeek, Zhipu, Gemini, Groq, Mistral, xAI, OpenRouter, and more
- **Subscription**: Anthropic (Claude CLI), Google OAuth
- **Local**: Ollama
- **AWS**: Bedrock

Configure providers in Settings → LLM Providers.

## Risk Controls

- Daily/weekly drawdown halts
- Max single trade loss limits
- Kelly criterion position sizing
- Strategy kill switches
- Emergency stop

## License

TBD
