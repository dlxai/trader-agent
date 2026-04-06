# Polymarket Trader

A standalone, event-driven Polymarket trading plugin built as an OpenClaw extension. Designed for **stable continuous profitability** on Polymarket prediction markets via WebSocket-driven signal detection, LLM-based judgment, and Kelly-sized paper trading with strict risk controls.

## Architecture

- **TypeScript plugin** (this repo) running inside an OpenClaw-compatible host (e.g. RivonClaw). Houses the **Collector** (WebSocket subscription, rolling stats, trigger detection) and the **Executor** (Kelly sizing, four-route exit monitor, circuit breakers).
- **Two OpenClaw agents** ("员工") configured separately by the user:
  - `polymarket-analyzer` — judges signal truth on every trigger event.
  - `polymarket-reviewer` — runs daily via OpenClaw cron, reads the trade journal, computes per-bucket win rates, generates filter proposals and kill-switch decisions.
- **State** lives in an independent SQLite file at `~/.polymarket-trader/data.db`. Reports go to `~/.polymarket-trader/reports/`.

## Independence

This project has **zero dependencies** on RivonClaw or `@mariozechner/openclaw` packages. The OpenClaw plugin API surface is inlined as `src/plugin-sdk.ts` (~30 lines of types and one `definePlugin()` helper). `pnpm install && pnpm build` from a fresh clone produces a self-contained `dist/polymarket-trader.mjs` you can drop into any OpenClaw runtime.

## Status

Spec and implementation plan are in `docs/specs/` and `docs/plans/`. Implementation has not started.

## License

TBD
