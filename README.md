# Polymarket Trader

A desktop application for Polymarket trading with AI-powered analysis, risk management, and real-time market monitoring. Supports both **standalone Electron mode** and **OpenClaw plugin mode**.

## Features

- **Real-time Market Data**: WebSocket-driven data collection from Polymarket
- **AI-Powered Analysis**: Three specialized AI agents (Analyzer, Reviewer, Risk Manager)
- **Multi-Provider LLM Support**: 24+ providers including OpenAI, Anthropic, Gemini, DeepSeek, and more
- **Risk Management**: Automatic circuit breakers, drawdown protection, and Kelly criterion position sizing
- **Auto-Apply Filter Proposals**: High-confidence trading parameter adjustments
- **Desktop Notifications**: Critical alerts and warnings via OS notifications
- **Chat Interface**: Interactive Hall chat with all three agents
- **OpenClaw Integration**: Run as OpenClaw plugin with cron-based scheduling

## Architecture

Monorepo structure with 4 packages:

- `@pmt/engine` - Trading engine (collector, executor, database) + OpenClaw plugin SDK
- `@pmt/llm` - LLM provider abstraction and agent runners
- `@pmt/main` - Electron main process with OpenClaw bridge
- `@pmt/renderer` - React UI

### Running Modes

1. **Standalone Mode** (default): Built-in schedulers for Reviewer (daily) and Coordinator (hourly)
2. **OpenClaw Plugin Mode**: OpenClaw manages agent scheduling via cron triggers

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

### OpenClaw Plugin Mode

Run as an OpenClaw plugin with external scheduling:

```bash
# Start in OpenClaw plugin mode (Windows)
pnpm start:openclaw

# Or set environment variable manually
set OPENCLAW_PLUGIN_MODE=true
pnpm start
```

In OpenClaw mode:
- Reviewer runs on cron schedule `0 0 * * *` (daily at midnight)
- Coordinator runs on cron schedule `0 * * * *` (hourly)
- Analyzer triggers on trading signals
- Electron UI receives events via the OpenClaw bridge

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
