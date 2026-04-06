# Polymarket Trader

A standalone, event-driven Polymarket trading plugin built as an OpenClaw extension. Designed for **stable continuous profitability** on Polymarket prediction markets via WebSocket-driven signal detection, LLM-based judgment, and Kelly-sized paper trading with strict risk controls.

## Architecture

- **TypeScript plugin** (this repo) running inside an OpenClaw-compatible host (e.g. RivonClaw). Houses the **Collector** (WebSocket subscription, rolling stats, trigger detection) and the **Executor** (Kelly sizing, four-route exit monitor, circuit breakers).
- **Two OpenClaw agents** ("员工") configured separately by the user:
  - `polymarket-analyzer` — judges signal truth on every trigger event.
  - `polymarket-reviewer` — runs daily via OpenClaw cron, reads the trade journal, computes per-bucket win rates, generates filter proposals and kill-switch decisions.
- **State** lives in `~/.polymarket-trader/data.db`. Reports go to `~/.polymarket-trader/reports/`.

## Isolation from existing OpenClaw / RivonClaw installations

This project runs OpenClaw with a **dedicated `OPENCLAW_HOME`** so it never touches `~/.openclaw/` or any other OpenClaw instance you may have on the same machine. All cron jobs, agent workspaces, sessions, and config live under `~/.polymarket-trader/openclaw/`.

```
~/.polymarket-trader/
├── openclaw/                  # OPENCLAW_HOME — fully isolated OpenClaw config
│   ├── openclaw.json
│   ├── agents/
│   │   ├── polymarket-analyzer/
│   │   └── polymarket-reviewer/
│   └── cron/jobs.json
├── data.db                    # plugin SQLite (sibling to openclaw/)
└── reports/                   # Reviewer markdown output
```

**Start the project's OpenClaw instance:**

```bash
# macOS / Linux
export OPENCLAW_HOME="$HOME/.polymarket-trader/openclaw"
openclaw start

# Windows PowerShell
$env:OPENCLAW_HOME = "$env:USERPROFILE\.polymarket-trader\openclaw"
openclaw start
```

You can keep your existing RivonClaw or other OpenClaw setup running concurrently — they use the default `~/.openclaw/` and never see this project's state.

**Optional override:** Set `POLYMARKET_TRADER_HOME` to put `data.db` and `reports/` somewhere other than `~/.polymarket-trader/`.

## Independence

This project has **zero dependencies** on RivonClaw or `@mariozechner/openclaw` packages. The OpenClaw plugin API surface is inlined as `src/plugin-sdk.ts` (~30 lines of types and one `definePlugin()` helper). `pnpm install && pnpm build` from a fresh clone produces a self-contained `dist/polymarket-trader.mjs` you can drop into any OpenClaw runtime.

## Status

Spec and implementation plan are in `docs/specs/` and `docs/plans/`. Implementation has not started.

## License

TBD
