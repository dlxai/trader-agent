# Polymarket Trader Desktop Application — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing Polymarket trading engine in a standalone Electron desktop application with React UI, 24+ LLM provider integration, and 3 chat-capable agent employees (Analyzer / Reviewer / Risk Manager-Coordinator).

**Architecture:** Monorepo with 4 packages: `engine` (existing trading logic, 160 tests), `llm` (5 adapters covering 24+ providers via OpenAI-compatible base + Anthropic + Gemini + Bedrock + Ollama), `main` (Electron main process hosting engine + IPC + tray + Coordinator scheduler), `renderer` (React 18 + Vite + Zustand UI in Kraken DESIGN.md style across 4 pages: Dashboard / Settings / Reports / Chat).

**Tech Stack:** TypeScript, Node.js 24+, Electron 30+, React 18, Vite 5, Zustand, React Router 7, Recharts, better-sqlite3, ws, @anthropic-ai/sdk, openai (compat), @google/generative-ai, @aws-sdk/client-bedrock-runtime, electron-builder, vitest.

**Spec reference:** `docs/specs/2026-04-07-desktop-app-design.md`

---

## Existing Code (do not modify, only relocate)

The current `D:/work/polymarket-trader/` repository contains a fully tested trading engine at HEAD `7124d66`:

- 48 commits of engine work, 160 tests passing
- Files at `src/{collector,executor,db,bus,config,recovery,reviewer,analyzer,util}/`
- Tests at `tests/{collector,executor,db,...}/`
- Build: `pnpm build` produces `dist/polymarket-trader.mjs`
- 3 files to DELETE during this plan: `src/index.ts`, `src/plugin-sdk.ts`, `tests/plugin-sdk.test.ts`

The plan **moves all of this** under `packages/engine/` in M1, then builds 3 new packages alongside it.

---

## File Structure

After M7 the repo looks like this:

```
polymarket-trader/                      # repo root
├── package.json                        # workspaces root
├── pnpm-workspace.yaml                 # NEW: workspaces declaration
├── tsconfig.base.json                  # MOVED to root from packages/engine
├── electron-builder.config.json        # NEW
├── .gitignore                          # extended for dist/, .vite/, electron-builder/
├── README.md                           # MODIFIED: install + run + features
│
├── packages/
│   │
│   ├── engine/                         # MOVED from src/* and tests/*
│   │   ├── package.json                # NEW: name "@pmt/engine"
│   │   ├── tsconfig.json               # MOVED, extends ../../tsconfig.base.json
│   │   ├── tsdown.config.ts            # MOVED
│   │   ├── vitest.config.ts            # MOVED
│   │   ├── src/
│   │   │   ├── (everything from old src/ EXCEPT index.ts and plugin-sdk.ts)
│   │   │   ├── collector/              # 6 files: bot-filter, rolling-window, trigger-evaluator, market-state, ws-client, collector
│   │   │   ├── executor/               # 8 files: kelly, pnl, circuit-breaker, position-tracker, paper-fill, exit-monitor, conflict-lock, executor + price-bucket
│   │   │   ├── db/                     # 9 files: connection, migrations, types, schema.sql, signal-log-repo, portfolio-state-repo, filter-config-repo, filter-proposals-repo, kill-switch-repo, strategy-performance-repo
│   │   │   ├── bus/                    # 2 files: events, types
│   │   │   ├── config/                 # 3 files: schema, defaults, loader
│   │   │   ├── recovery/               # 1 file: startup-recovery
│   │   │   ├── reviewer/               # 4 files: statistics, kill-switch-decider, report-generator, reviewer
│   │   │   │                           # plus alert-dispatcher
│   │   │   ├── analyzer/               # 2 files: verdict-parser, context-packer
│   │   │   │                           # (analyzer-client.ts DELETED — replaced by packages/llm runner)
│   │   │   └── util/                   # 2 files: time, errors
│   │   ├── tests/                      # MOVED from tests/, all 160 keep passing
│   │   └── docs/                       # contains AGENTS-analyzer.md, AGENTS-reviewer.md, m4-runbook.md
│   │
│   ├── llm/                            # NEW package: provider abstraction + agent runners
│   │   ├── package.json                # NEW: name "@pmt/llm"
│   │   ├── tsconfig.json               # NEW
│   │   ├── tsdown.config.ts            # NEW
│   │   ├── vitest.config.ts            # NEW
│   │   ├── src/
│   │   │   ├── index.ts                # public exports
│   │   │   ├── provider.ts             # LlmProvider interface
│   │   │   ├── types.ts                # ChatMessage, ProviderId, AgentId, etc.
│   │   │   ├── adapters/
│   │   │   │   ├── openai-compat.ts    # base for 19 providers
│   │   │   │   ├── anthropic.ts        # API key + CLI subscription
│   │   │   │   ├── gemini.ts           # API key + Google OAuth
│   │   │   │   ├── bedrock.ts          # AWS Bedrock
│   │   │   │   └── ollama.ts           # local HTTP
│   │   │   ├── registry.ts             # provider registry + per-agent assignment
│   │   │   ├── routing.ts              # "Prefer Subscription" router
│   │   │   ├── credentials.ts          # secret store interface (impl in main package)
│   │   │   └── runners/
│   │   │       ├── analyzer-runner.ts  # replaces engine's analyzer-client stub
│   │   │       ├── reviewer-runner.ts  # invokes Reviewer prompt
│   │   │       ├── risk-mgr-runner.ts  # reactive + proactive Coordinator
│   │   │       └── personas/
│   │   │           ├── analyzer.ts     # system prompt + context packer
│   │   │           ├── reviewer.ts     # system prompt for daily review
│   │   │           └── risk-manager.ts # system prompt for queries + Coordinator
│   │   └── tests/
│   │       ├── adapters/
│   │       │   ├── openai-compat.test.ts
│   │       │   ├── anthropic.test.ts
│   │       │   └── gemini.test.ts
│   │       ├── routing.test.ts
│   │       ├── runners/
│   │       │   ├── analyzer-runner.test.ts
│   │       │   ├── reviewer-runner.test.ts
│   │       │   └── risk-mgr-runner.test.ts
│   │       └── registry.test.ts
│   │
│   ├── main/                           # NEW package: Electron main process
│   │   ├── package.json                # NEW: name "@pmt/main"
│   │   ├── tsconfig.json               # NEW
│   │   ├── tsdown.config.ts            # NEW
│   │   ├── vitest.config.ts            # NEW
│   │   ├── src/
│   │   │   ├── index.ts                # Electron app entry
│   │   │   ├── window.ts               # main window mgmt
│   │   │   ├── tray.ts                 # system tray
│   │   │   ├── lifecycle.ts            # bootEngine() / shutdownEngine()
│   │   │   ├── ipc.ts                  # all IPC handlers
│   │   │   ├── preload.ts              # contextBridge typed API
│   │   │   ├── secrets.ts              # safeStorage wrapper
│   │   │   ├── coordinator.ts          # hourly Coordinator scheduler
│   │   │   ├── reviewer-scheduler.ts   # daily Reviewer scheduler
│   │   │   ├── auto-apply.ts           # high-confidence filter_proposals auto-apply
│   │   │   ├── notifications.ts        # OS desktop notifications
│   │   │   └── db-extensions.ts        # adds 4 new tables to engine DB
│   │   └── tests/
│   │       ├── secrets.test.ts
│   │       ├── auto-apply.test.ts
│   │       └── coordinator.test.ts
│   │
│   └── renderer/                       # NEW package: React UI
│       ├── package.json                # NEW: name "@pmt/renderer"
│       ├── tsconfig.json               # NEW
│       ├── vite.config.ts              # NEW
│       ├── vitest.config.ts            # NEW
│       ├── index.html                  # NEW Vite entry HTML
│       ├── DESIGN.md                   # NEW: copied from awesome-design-md/kraken
│       ├── src/
│       │   ├── main.tsx                # React + ReactDOM bootstrap
│       │   ├── App.tsx                 # Router + sidebar layout
│       │   ├── ipc-client.ts           # typed wrapper over window.pmt
│       │   ├── theme.ts                # Kraken design tokens (colors, spacing, radius)
│       │   ├── pages/
│       │   │   ├── Dashboard.tsx
│       │   │   ├── Settings.tsx
│       │   │   ├── Reports.tsx
│       │   │   └── Chat.tsx
│       │   ├── components/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── KpiCard.tsx
│       │   │   ├── PositionTable.tsx
│       │   │   ├── CoordinatorBanner.tsx
│       │   │   ├── ProviderCard.tsx
│       │   │   ├── ProposalCard.tsx
│       │   │   ├── ReportListItem.tsx
│       │   │   ├── BucketTable.tsx
│       │   │   ├── ChatMessage.tsx
│       │   │   ├── ChatInput.tsx
│       │   │   └── EmployeeTab.tsx
│       │   ├── stores/
│       │   │   ├── portfolio.ts        # Zustand
│       │   │   ├── positions.ts
│       │   │   ├── chat.ts
│       │   │   ├── coordinator.ts
│       │   │   └── settings.ts
│       │   └── styles/
│       │       └── global.css
│       └── tests/
│           ├── components/
│           │   ├── PositionTable.test.tsx
│           │   └── KpiCard.test.tsx
│           └── pages/
│               └── Dashboard.test.tsx
│
└── docs/
    ├── specs/                          # unchanged
    │   ├── 2026-04-06-polymarket-trading-agents-design.md
    │   └── 2026-04-07-desktop-app-design.md
    └── plans/                          # this plan lives here
        ├── 2026-04-06-polymarket-trader-plugin.md
        ├── 2026-04-07-desktop-app-plan.md
        └── I1-I2-findings.md
```

---

## Investigation Tasks (do these BEFORE M1)

Three unknowns the plan depends on. Resolve via short investigation, document findings, then proceed.

### Investigation I3: better-sqlite3 native rebuild for Electron

The engine uses `better-sqlite3` which compiles native C++ bindings against the Node.js version it was installed for. Electron uses its own bundled Node, so the engine's prebuilt binary may not load inside Electron without rebuild.

- [ ] **Step 1: Read better-sqlite3 docs on Electron compatibility**

Run: `find D:/work/polymarket-trader/node_modules/better-sqlite3 -name "*.md" 2>/dev/null | xargs grep -l -i "electron"`
Read every match. Look for: install hooks, rebuild commands, prebuild support.

- [ ] **Step 2: Document the rebuild approach**

Write to `docs/plans/I3-findings.md`:

```markdown
# I3: better-sqlite3 + Electron native rebuild

**Approach:** [chosen approach]

**Required postinstall script:** [exact command]

**Verification:** [how to confirm engine works inside Electron at runtime]

**Risk:** [if rebuild fails on a target platform]
```

Three plausible approaches:
- (a) `electron-rebuild` postinstall — rebuild bindings against Electron's Node version
- (b) `@electron/rebuild` (newer fork)
- (c) bundle prebuilt Electron-compatible binaries via better-sqlite3-multiple-ciphers or similar

Pick one and document why.

- [ ] **Step 3: Commit findings**

```bash
cd D:/work/polymarket-trader
git add docs/plans/I3-findings.md
git commit -m "docs(plan): record I3 findings on better-sqlite3 + Electron rebuild"
```

### Investigation I4: Anthropic Subscription CLI credentials format

The desktop app needs to detect existing Claude Code / Claude CLI credentials so users with an Anthropic Max/Pro subscription don't need to paste an API key.

- [ ] **Step 1: Find the credentials file location**

Check these paths (whichever exists on the dev machine):
- `~/.claude/credentials.json`
- `~/.claude/.credentials.json`
- `~/.config/claude/credentials.json` (Linux)
- `%APPDATA%\Claude\credentials.json` (Windows)

Run: `find ~/.claude -type f -name "*.json" 2>/dev/null` and `dir "%USERPROFILE%\.claude" 2>/dev/null`

- [ ] **Step 2: Document the schema**

Write to `docs/plans/I4-findings.md`:

```markdown
# I4: Anthropic CLI credentials format

**File location by OS:**
- macOS/Linux: [path]
- Windows: [path]

**Schema:**
```json
[paste sanitized example with secrets redacted]
```

**Fields needed:** [which fields the AnthropicAdapter must read]

**Refresh logic:** [does it auto-refresh? how to detect expiry?]

**Fallback:** if file missing, prompt user to install Claude CLI and run `claude login`
```

- [ ] **Step 3: Commit**

```bash
git add docs/plans/I4-findings.md
git commit -m "docs(plan): record I4 findings on Anthropic CLI credentials"
```

### Investigation I5: Google OAuth flow in Electron

The Gemini adapter supports both API key and Google OAuth (free tier). OAuth in Electron requires opening a browser window for user consent.

- [ ] **Step 1: Research approach**

Read: https://www.electronjs.org/docs/latest/tutorial/launch-app-from-url-in-another-app
Read: https://github.com/googleapis/google-auth-library-nodejs

Three approaches:
- (a) Open OAuth consent URL in user's default browser, listen on a localhost callback (most user-friendly)
- (b) Open in an Electron BrowserWindow, intercept the redirect
- (c) Use device flow (no browser needed, user gets a code to paste)

- [ ] **Step 2: Document chosen approach**

Write to `docs/plans/I5-findings.md`:

```markdown
# I5: Gemini OAuth in Electron

**Chosen approach:** [a/b/c with rationale]

**Required scopes:** generative-language.api or whatever's correct

**Token storage:** OS keychain via Electron safeStorage

**Token refresh:** [auto-refresh strategy]

**Fallback:** prompt user to paste API key instead
```

- [ ] **Step 3: Commit**

```bash
git add docs/plans/I5-findings.md
git commit -m "docs(plan): record I5 findings on Gemini OAuth flow"
```

---

## M1 — Foundation (Monorepo + Engine Relocation)

Goal: convert the repo into a pnpm workspace, move existing engine to `packages/engine/`, scaffold the 3 new packages with empty stubs that build cleanly. All 160 existing tests must keep passing after the move.

### Task M1.1: Initialize pnpm workspace

**Files:**
- Create: `pnpm-workspace.yaml`
- Modify: `package.json`
- Create: `tsconfig.base.json`
- Modify: `.gitignore`

- [ ] **Step 1: Create `pnpm-workspace.yaml`**

```yaml
packages:
  - "packages/*"
```

- [ ] **Step 2: Replace root `package.json`**

```json
{
  "name": "polymarket-trader",
  "private": true,
  "version": "0.2.0",
  "description": "Standalone Polymarket trading desktop application",
  "type": "module",
  "scripts": {
    "build": "pnpm -r build",
    "test": "pnpm -r test",
    "test:run": "pnpm -r test:run",
    "typecheck": "pnpm -r typecheck",
    "clean": "pnpm -r clean"
  },
  "devDependencies": {
    "typescript": "^5.8.2",
    "@types/node": "^22.10.5"
  },
  "engines": {
    "node": ">=24",
    "pnpm": ">=10"
  }
}
```

- [ ] **Step 3: Create `tsconfig.base.json` at repo root**

```json
{
  "compilerOptions": {
    "module": "ESNext",
    "target": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "declaration": true,
    "sourceMap": false
  }
}
```

- [ ] **Step 4: Update `.gitignore` to cover new package output dirs**

Append to existing `.gitignore`:

```
# Per-package build outputs
packages/*/dist/
packages/*/.turbo/
packages/renderer/.vite/
packages/renderer/dist-electron/

# Electron-builder output
dist-electron/
release/
```

- [ ] **Step 5: Verify pnpm picks up the workspace**

Run: `cd D:/work/polymarket-trader && pnpm install --workspace-root`
Expected: Installs root devDeps without error, no warning about missing workspace packages.

- [ ] **Step 6: Commit**

```bash
git add pnpm-workspace.yaml package.json tsconfig.base.json .gitignore
git commit -m "feat(monorepo): initialize pnpm workspace at repo root"
```

### Task M1.2: Relocate engine code to `packages/engine/`

**Files:** moves only — no content changes

- [ ] **Step 1: Create directory and move source/test trees**

```bash
cd D:/work/polymarket-trader
mkdir -p packages/engine
git mv src packages/engine/src
git mv tests packages/engine/tests
git mv tsconfig.json packages/engine/tsconfig.json
git mv tsdown.config.ts packages/engine/tsdown.config.ts
git mv vitest.config.ts packages/engine/vitest.config.ts
git mv openclaw.plugin.json packages/engine/openclaw.plugin.json
```

- [ ] **Step 2: Delete files no longer needed**

```bash
git rm packages/engine/src/index.ts
git rm packages/engine/src/plugin-sdk.ts
git rm packages/engine/tests/plugin-sdk.test.ts
git rm packages/engine/tests/smoke.test.ts
git rm packages/engine/openclaw.plugin.json
```

These files were the OpenClaw plugin shim. The new architecture has Electron main process import engine modules directly.

- [ ] **Step 3: Update `packages/engine/tsconfig.json` to extend root base**

Replace contents with:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

- [ ] **Step 4: Move root `package.json` deps into a new `packages/engine/package.json`**

Note: the OLD root package.json (before M1.1) had engine deps. After M1.1 the root is workspace-only. We need a NEW per-package manifest.

Create `packages/engine/package.json`:

```json
{
  "name": "@pmt/engine",
  "version": "0.2.0",
  "description": "Polymarket trading engine — collector, executor, repos, rules",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    },
    "./collector": {
      "types": "./dist/collector/index.d.ts",
      "import": "./dist/collector/index.js"
    },
    "./executor": {
      "types": "./dist/executor/index.d.ts",
      "import": "./dist/executor/index.js"
    },
    "./db": {
      "types": "./dist/db/index.d.ts",
      "import": "./dist/db/index.js"
    },
    "./bus": {
      "types": "./dist/bus/index.d.ts",
      "import": "./dist/bus/index.js"
    },
    "./config": {
      "types": "./dist/config/index.d.ts",
      "import": "./dist/config/index.js"
    },
    "./reviewer": {
      "types": "./dist/reviewer/index.d.ts",
      "import": "./dist/reviewer/index.js"
    },
    "./recovery": {
      "types": "./dist/recovery/index.d.ts",
      "import": "./dist/recovery/index.js"
    },
    "./analyzer": {
      "types": "./dist/analyzer/index.d.ts",
      "import": "./dist/analyzer/index.js"
    },
    "./util": {
      "types": "./dist/util/index.d.ts",
      "import": "./dist/util/index.js"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsdown",
    "test": "vitest",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "dependencies": {
    "better-sqlite3": "^11.10.0",
    "ws": "^8.18.0"
  },
  "devDependencies": {
    "@types/better-sqlite3": "^7.6.11",
    "@types/ws": "^8.5.12",
    "tsdown": "^0.20.3",
    "vitest": "^4.1.2",
    "@vitest/coverage-v8": "^4.1.2"
  }
}
```

- [ ] **Step 5: Create barrel `src/index.ts` re-exports**

Each subpath in `exports` needs an `index.ts` barrel that re-exports its public API. Create the following files:

`packages/engine/src/index.ts`:
```typescript
export * from "./collector/index.js";
export * from "./executor/index.js";
export * from "./db/index.js";
export * from "./bus/index.js";
export * from "./config/index.js";
export * from "./reviewer/index.js";
export * from "./recovery/index.js";
export * from "./analyzer/index.js";
export * from "./util/index.js";
```

`packages/engine/src/collector/index.ts`:
```typescript
export * from "./bot-filter.js";
export * from "./rolling-window.js";
export * from "./trigger-evaluator.js";
export * from "./market-state.js";
export * from "./ws-client.js";
export * from "./collector.js";
```

`packages/engine/src/executor/index.ts`:
```typescript
export * from "./kelly.js";
export * from "./pnl.js";
export * from "./circuit-breaker.js";
export * from "./position-tracker.js";
export * from "./paper-fill.js";
export * from "./exit-monitor.js";
export * from "./conflict-lock.js";
export * from "./executor.js";
export * from "./price-bucket.js";
```

`packages/engine/src/db/index.ts`:
```typescript
export * from "./connection.js";
export * from "./migrations.js";
export * from "./types.js";
export * from "./signal-log-repo.js";
export * from "./portfolio-state-repo.js";
export * from "./filter-config-repo.js";
export * from "./filter-proposals-repo.js";
export * from "./kill-switch-repo.js";
export * from "./strategy-performance-repo.js";
```

`packages/engine/src/bus/index.ts`:
```typescript
export * from "./events.js";
export * from "./types.js";
```

`packages/engine/src/config/index.ts`:
```typescript
export * from "./schema.js";
export * from "./defaults.js";
export * from "./loader.js";
```

`packages/engine/src/reviewer/index.ts`:
```typescript
export * from "./statistics.js";
export * from "./kill-switch-decider.js";
export * from "./report-generator.js";
export * from "./reviewer.js";
export * from "./alert-dispatcher.js";
```

`packages/engine/src/recovery/index.ts`:
```typescript
export * from "./startup-recovery.js";
```

`packages/engine/src/analyzer/index.ts`:
```typescript
export * from "./verdict-parser.js";
export * from "./context-packer.js";
```

`packages/engine/src/util/index.ts`:
```typescript
export * from "./time.js";
export * from "./errors.js";
```

- [ ] **Step 6: Update `tsdown.config.ts` for multi-entry build**

Replace `packages/engine/tsdown.config.ts`:

```typescript
import { defineConfig } from "tsdown";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    "collector/index": "src/collector/index.ts",
    "executor/index": "src/executor/index.ts",
    "db/index": "src/db/index.ts",
    "bus/index": "src/bus/index.ts",
    "config/index": "src/config/index.ts",
    "reviewer/index": "src/reviewer/index.ts",
    "recovery/index": "src/recovery/index.ts",
    "analyzer/index": "src/analyzer/index.ts",
    "util/index": "src/util/index.ts",
  },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["better-sqlite3", "ws"],
  outExtensions: () => ({ dts: ".d.ts" }),
  onSuccess: async () => {
    const { copyFileSync, mkdirSync } = await import("node:fs");
    const { join } = await import("node:path");
    mkdirSync(join(process.cwd(), "dist", "db"), { recursive: true });
    copyFileSync(
      join(process.cwd(), "src", "db", "schema.sql"),
      join(process.cwd(), "dist", "db", "schema.sql")
    );
  },
});
```

The earlier `openclaw.plugin.json` copy is removed since this is no longer a plugin.

- [ ] **Step 7: Install workspace and run engine tests**

```bash
cd D:/work/polymarket-trader
pnpm install
pnpm --filter @pmt/engine build
pnpm --filter @pmt/engine test:run
```

Expected:
- `pnpm install` succeeds, hoists deps to `node_modules/`
- `pnpm build` succeeds, creates `packages/engine/dist/`
- `pnpm test:run` shows **160 tests passing** (the same as before relocation)

If tests fail because they import from `../../src/db/migrations.js` style relative paths, those should still work since the relative file structure inside `packages/engine/` is unchanged.

- [ ] **Step 8: Commit**

```bash
git add packages/engine/ pnpm-lock.yaml
git commit -m "feat(monorepo): relocate engine to packages/engine/ + add subpath barrels"
```

### Task M1.3: Scaffold empty `packages/llm`

**Files:**
- Create: `packages/llm/package.json`
- Create: `packages/llm/tsconfig.json`
- Create: `packages/llm/tsdown.config.ts`
- Create: `packages/llm/vitest.config.ts`
- Create: `packages/llm/src/index.ts` (placeholder)
- Create: `packages/llm/tests/smoke.test.ts`

- [ ] **Step 1: `packages/llm/package.json`**

```json
{
  "name": "@pmt/llm",
  "version": "0.2.0",
  "description": "LLM provider abstraction and agent runners for Polymarket Trader",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": { "types": "./dist/index.d.ts", "import": "./dist/index.js" }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsdown",
    "test": "vitest",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "dependencies": {
    "@pmt/engine": "workspace:*",
    "@anthropic-ai/sdk": "^0.30.0",
    "openai": "^4.70.0",
    "@google/generative-ai": "^0.21.0"
  },
  "devDependencies": {
    "tsdown": "^0.20.3",
    "vitest": "^4.1.2"
  }
}
```

- [ ] **Step 2: `packages/llm/tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

- [ ] **Step 3: `packages/llm/tsdown.config.ts`**

```typescript
import { defineConfig } from "tsdown";

export default defineConfig({
  entry: { index: "src/index.ts" },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["@pmt/engine", "@anthropic-ai/sdk", "openai", "@google/generative-ai"],
  outExtensions: () => ({ dts: ".d.ts" }),
});
```

- [ ] **Step 4: `packages/llm/vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    globals: false,
  },
});
```

- [ ] **Step 5: Stub `packages/llm/src/index.ts`**

```typescript
// @pmt/llm — LLM provider abstraction. Real implementation arrives in M2.
export const PACKAGE_NAME = "@pmt/llm";
```

- [ ] **Step 6: Smoke test `packages/llm/tests/smoke.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { PACKAGE_NAME } from "../src/index.js";

describe("@pmt/llm smoke", () => {
  it("package loads", () => {
    expect(PACKAGE_NAME).toBe("@pmt/llm");
  });
});
```

- [ ] **Step 7: Install + build + test**

```bash
cd D:/work/polymarket-trader
pnpm install
pnpm --filter @pmt/llm build
pnpm --filter @pmt/llm test:run
```

Expected: build success, 1 smoke test passing.

- [ ] **Step 8: Commit**

```bash
git add packages/llm/ pnpm-lock.yaml
git commit -m "feat(llm): scaffold @pmt/llm package with smoke test"
```

### Task M1.4: Scaffold empty `packages/main`

**Files:**
- Create: `packages/main/package.json`
- Create: `packages/main/tsconfig.json`
- Create: `packages/main/tsdown.config.ts`
- Create: `packages/main/vitest.config.ts`
- Create: `packages/main/src/index.ts` (placeholder, no Electron yet)
- Create: `packages/main/tests/smoke.test.ts`

- [ ] **Step 1: `packages/main/package.json`**

```json
{
  "name": "@pmt/main",
  "version": "0.2.0",
  "description": "Electron main process for Polymarket Trader Desktop",
  "type": "module",
  "main": "./dist/index.js",
  "scripts": {
    "build": "tsdown",
    "test": "vitest",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "dependencies": {
    "@pmt/engine": "workspace:*",
    "@pmt/llm": "workspace:*"
  },
  "devDependencies": {
    "electron": "^30.0.0",
    "tsdown": "^0.20.3",
    "vitest": "^4.1.2"
  }
}
```

Note: Electron itself goes in devDependencies because it's bundled into the final package by electron-builder, not loaded from node_modules at runtime.

- [ ] **Step 2: `packages/main/tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "module": "ESNext"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

- [ ] **Step 3: `packages/main/tsdown.config.ts`**

```typescript
import { defineConfig } from "tsdown";

export default defineConfig({
  entry: { index: "src/index.ts" },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["@pmt/engine", "@pmt/llm", "electron", "better-sqlite3", "ws"],
  outExtensions: () => ({ dts: ".d.ts" }),
});
```

- [ ] **Step 4: `packages/main/vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    globals: false,
  },
});
```

- [ ] **Step 5: Stub `packages/main/src/index.ts`**

```typescript
// @pmt/main — Electron main process. Real implementation arrives in M3.
export const PACKAGE_NAME = "@pmt/main";
```

- [ ] **Step 6: Smoke test `packages/main/tests/smoke.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { PACKAGE_NAME } from "../src/index.js";

describe("@pmt/main smoke", () => {
  it("package loads", () => {
    expect(PACKAGE_NAME).toBe("@pmt/main");
  });
});
```

- [ ] **Step 7: Install + build + test + commit**

```bash
cd D:/work/polymarket-trader
pnpm install
pnpm --filter @pmt/main build
pnpm --filter @pmt/main test:run
git add packages/main/ pnpm-lock.yaml
git commit -m "feat(main): scaffold @pmt/main package with smoke test"
```

### Task M1.5: Scaffold empty `packages/renderer`

**Files:**
- Create: `packages/renderer/package.json`
- Create: `packages/renderer/tsconfig.json`
- Create: `packages/renderer/vite.config.ts`
- Create: `packages/renderer/vitest.config.ts`
- Create: `packages/renderer/index.html`
- Create: `packages/renderer/src/main.tsx` (placeholder)
- Create: `packages/renderer/tests/smoke.test.tsx`

- [ ] **Step 1: `packages/renderer/package.json`**

```json
{
  "name": "@pmt/renderer",
  "version": "0.2.0",
  "description": "React renderer for Polymarket Trader Desktop",
  "type": "module",
  "scripts": {
    "build": "vite build",
    "dev": "vite",
    "test": "vitest",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist .vite"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "vite": "^5.4.10",
    "vitest": "^4.1.2",
    "@testing-library/react": "^16.0.1",
    "@testing-library/jest-dom": "^6.6.3",
    "jsdom": "^25.0.1"
  }
}
```

- [ ] **Step 2: `packages/renderer/tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "module": "ESNext",
    "moduleResolution": "bundler"
  },
  "include": ["src/**/*", "tests/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 3: `packages/renderer/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
```

- [ ] **Step 4: `packages/renderer/vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    globals: false,
    setupFiles: [],
  },
});
```

- [ ] **Step 5: `packages/renderer/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Polymarket Trader</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Stub `packages/renderer/src/main.tsx`**

```typescript
import React from "react";
import { createRoot } from "react-dom/client";

function App() {
  return <div>Polymarket Trader — placeholder, real UI in M4</div>;
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<App />);
}

export const PACKAGE_NAME = "@pmt/renderer";
```

- [ ] **Step 7: Smoke test `packages/renderer/tests/smoke.test.tsx`**

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

function Hello() {
  return <span>hello</span>;
}

describe("@pmt/renderer smoke", () => {
  it("renders a React component", () => {
    render(<Hello />);
    expect(screen.getByText("hello")).toBeDefined();
  });
});
```

- [ ] **Step 8: Install + build + test + commit**

```bash
cd D:/work/polymarket-trader
pnpm install
pnpm --filter @pmt/renderer build
pnpm --filter @pmt/renderer test:run
git add packages/renderer/ pnpm-lock.yaml
git commit -m "feat(renderer): scaffold @pmt/renderer package with smoke test"
```

### Task M1.6: Run full workspace build + test

After all four packages exist, verify the whole monorepo builds and tests cleanly.

- [ ] **Step 1: Clean + reinstall + build all packages**

```bash
cd D:/work/polymarket-trader
pnpm clean
pnpm install
pnpm build
```

Expected: 4 packages each build their `dist/`. No errors.

- [ ] **Step 2: Run all tests**

```bash
pnpm test:run
```

Expected: 162 tests passing (160 engine + 1 llm smoke + 1 main smoke + 1 renderer smoke = 163 actually).

If the renderer test count is short, run `pnpm --filter @pmt/renderer test:run` separately to see why.

- [ ] **Step 3: Run full type-check**

```bash
pnpm typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit any cleanup**

If anything was modified during verification:

```bash
git add -A
git commit -m "chore(monorepo): post-relocation cleanup and verification"
```

### Task M1.7: Add 4 new tables to engine schema (chat_messages, coordinator_log, llm_provider_state, app_state)

The engine already owns the SQLite database. Adding new tables means extending the schema in `packages/engine/src/db/schema.sql` and bumping the migration version.

**Files:**
- Modify: `packages/engine/src/db/schema.sql`
- Modify: `packages/engine/src/db/migrations.ts`
- Create: `packages/engine/tests/db/new-tables.test.ts`

- [ ] **Step 1: Write the failing test**

Create `packages/engine/tests/db/new-tables.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "../../src/db/migrations.js";

describe("M1.7 new tables migration", () => {
  let db: Database.Database;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
  });

  it("creates chat_messages table with all required columns", () => {
    const cols = db.prepare("PRAGMA table_info(chat_messages)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("message_id");
    expect(names).toContain("agent_id");
    expect(names).toContain("role");
    expect(names).toContain("content");
    expect(names).toContain("model_used");
    expect(names).toContain("provider_used");
    expect(names).toContain("tokens_input");
    expect(names).toContain("tokens_output");
    expect(names).toContain("created_at");
  });

  it("creates coordinator_log table", () => {
    const cols = db.prepare("PRAGMA table_info(coordinator_log)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("log_id");
    expect(names).toContain("generated_at");
    expect(names).toContain("summary");
    expect(names).toContain("alerts");
    expect(names).toContain("suggestions");
    expect(names).toContain("context_snapshot");
  });

  it("creates llm_provider_state table", () => {
    const cols = db.prepare("PRAGMA table_info(llm_provider_state)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("provider_id");
    expect(names).toContain("is_connected");
    expect(names).toContain("auth_type");
    expect(names).toContain("models_available");
    expect(names).toContain("quota_used");
    expect(names).toContain("quota_limit");
  });

  it("creates app_state KV table", () => {
    const cols = db.prepare("PRAGMA table_info(app_state)").all() as Array<{ name: string }>;
    const names = cols.map((c) => c.name).sort();
    expect(names).toContain("key");
    expect(names).toContain("value");
    expect(names).toContain("updated_at");
  });

  it("rejects invalid agent_id in chat_messages", () => {
    expect(() =>
      db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run("invalid_agent", "user", "test", Date.now())
    ).toThrow();
  });

  it("rejects invalid role in chat_messages", () => {
    expect(() =>
      db
        .prepare(
          "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
        )
        .run("analyzer", "robot", "test", Date.now())
    ).toThrow();
  });
});
```

- [ ] **Step 2: Run, verify fails**

```bash
pnpm --filter @pmt/engine test:run tests/db/new-tables.test.ts
```

Expected: FAILS — "no such table" errors.

- [ ] **Step 3: Append new tables to `packages/engine/src/db/schema.sql`**

Add at the end of the existing file:

```sql
-- chat_messages: user/agent conversation history (M1.7 added by desktop app spec)
CREATE TABLE IF NOT EXISTS chat_messages (
  message_id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT NOT NULL CHECK (agent_id IN ('analyzer', 'reviewer', 'risk_manager')),
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  model_used TEXT,
  provider_used TEXT,
  tokens_input INTEGER,
  tokens_output INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_agent ON chat_messages(agent_id, created_at DESC);

-- coordinator_log: hourly Coordinator briefs from Risk Manager
CREATE TABLE IF NOT EXISTS coordinator_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_at INTEGER NOT NULL,
  summary TEXT NOT NULL,
  alerts TEXT NOT NULL DEFAULT '[]',
  suggestions TEXT NOT NULL DEFAULT '[]',
  context_snapshot TEXT NOT NULL,
  model_used TEXT,
  tokens_total INTEGER
);
CREATE INDEX IF NOT EXISTS idx_coordinator_log_time ON coordinator_log(generated_at DESC);

-- llm_provider_state: per-provider connection state and quota
CREATE TABLE IF NOT EXISTS llm_provider_state (
  provider_id TEXT PRIMARY KEY,
  is_connected INTEGER NOT NULL DEFAULT 0,
  auth_type TEXT NOT NULL CHECK (auth_type IN ('api_key', 'oauth', 'cli_credential', 'aws')),
  models_available TEXT NOT NULL DEFAULT '[]',
  quota_used INTEGER DEFAULT 0,
  quota_limit INTEGER,
  quota_resets_at INTEGER,
  last_check_at INTEGER NOT NULL,
  last_error TEXT
);

-- app_state: desktop app KV (window position, last selected page, etc.)
CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

- [ ] **Step 4: Bump `CURRENT_VERSION` to 2 in migrations.ts**

Edit `packages/engine/src/db/migrations.ts`, change:

```typescript
const CURRENT_VERSION = 1;
```

to:

```typescript
const CURRENT_VERSION = 2;
```

- [ ] **Step 5: Run, verify passes**

```bash
pnpm --filter @pmt/engine test:run tests/db/new-tables.test.ts
```

Expected: 6 tests pass.

- [ ] **Step 6: Run full engine tests, verify no regression**

```bash
pnpm --filter @pmt/engine test:run
pnpm --filter @pmt/engine build
```

Expected: All previously passing tests still pass + 6 new ones (166 total in engine).

- [ ] **Step 7: Commit**

```bash
git add packages/engine/src/db/schema.sql packages/engine/src/db/migrations.ts packages/engine/tests/db/new-tables.test.ts
git commit -m "feat(db): add chat_messages, coordinator_log, llm_provider_state, app_state tables"
```

### Task M1.8: Add Electron `safeStorage` wrapper to `packages/main`

Even though there's no Electron app yet, we need a typed wrapper around `safeStorage` so the LLM provider layer (M2) can call it without coupling itself to Electron.

**Files:**
- Create: `packages/main/src/secrets.ts`
- Create: `packages/main/tests/secrets.test.ts`

- [ ] **Step 1: Failing test at `packages/main/tests/secrets.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createSecretStore } from "../src/secrets.js";

// Mock electron's safeStorage
vi.mock("electron", () => ({
  safeStorage: {
    isEncryptionAvailable: () => true,
    encryptString: (s: string) => Buffer.from("enc:" + s),
    decryptString: (b: Buffer) => b.toString().replace(/^enc:/, ""),
  },
  app: {
    getPath: (kind: string) => {
      if (kind === "userData") return "/tmp/test-userdata-" + Math.random();
      throw new Error("unexpected getPath: " + kind);
    },
  },
}));

describe("secretStore", () => {
  let store: ReturnType<typeof createSecretStore>;

  beforeEach(() => {
    store = createSecretStore();
  });

  it("stores and retrieves an encrypted secret", async () => {
    await store.set("test-key", "secret-value");
    const value = await store.get("test-key");
    expect(value).toBe("secret-value");
  });

  it("returns null for unknown key", async () => {
    expect(await store.get("never-set")).toBeNull();
  });

  it("deletes a secret", async () => {
    await store.set("temp", "x");
    await store.delete("temp");
    expect(await store.get("temp")).toBeNull();
  });

  it("lists all keys", async () => {
    await store.set("a", "1");
    await store.set("b", "2");
    const keys = await store.listKeys();
    expect(keys.sort()).toEqual(["a", "b"]);
  });
});
```

- [ ] **Step 2: Run, verify fails (module not found)**

```bash
pnpm --filter @pmt/main test:run tests/secrets.test.ts
```

- [ ] **Step 3: Implement `packages/main/src/secrets.ts`**

```typescript
import { safeStorage, app } from "electron";
import { readFileSync, writeFileSync, existsSync, mkdirSync, unlinkSync, readdirSync } from "node:fs";
import { join } from "node:path";

export interface SecretStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  listKeys(): Promise<string[]>;
}

/**
 * Creates a secret store backed by Electron's safeStorage (platform keychain
 * on macOS/Windows, libsecret on Linux). Encrypted blobs are written to disk
 * as one file per key under app.getPath("userData") + "/secrets/".
 *
 * This wrapper exists so other packages (e.g. @pmt/llm) can store API keys
 * without taking a direct Electron dependency.
 */
export function createSecretStore(): SecretStore {
  const userDataDir = app.getPath("userData");
  const secretsDir = join(userDataDir, "secrets");
  mkdirSync(secretsDir, { recursive: true });

  function pathFor(key: string): string {
    if (!/^[A-Za-z0-9._-]+$/.test(key)) {
      throw new Error(`secretStore: invalid key '${key}' — only alphanumerics, dot, underscore, dash`);
    }
    return join(secretsDir, key + ".bin");
  }

  return {
    async get(key) {
      const path = pathFor(key);
      if (!existsSync(path)) return null;
      if (!safeStorage.isEncryptionAvailable()) {
        throw new Error("secretStore: OS encryption not available");
      }
      const blob = readFileSync(path);
      return safeStorage.decryptString(blob);
    },
    async set(key, value) {
      if (!safeStorage.isEncryptionAvailable()) {
        throw new Error("secretStore: OS encryption not available");
      }
      const blob = safeStorage.encryptString(value);
      writeFileSync(pathFor(key), blob);
    },
    async delete(key) {
      const path = pathFor(key);
      if (existsSync(path)) unlinkSync(path);
    },
    async listKeys() {
      if (!existsSync(secretsDir)) return [];
      return readdirSync(secretsDir)
        .filter((name) => name.endsWith(".bin"))
        .map((name) => name.slice(0, -4));
    },
  };
}
```

- [ ] **Step 4: Run test, verify pass**

```bash
pnpm --filter @pmt/main test:run tests/secrets.test.ts
```

Expected: 4 tests pass.

- [ ] **Step 5: Build**

```bash
pnpm --filter @pmt/main build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add packages/main/src/secrets.ts packages/main/tests/secrets.test.ts
git commit -m "feat(main): add Electron safeStorage wrapper for secret storage"
```

---

## M1 Verification Gate

After all M1 tasks:

- [ ] **Run full workspace test**

```bash
cd D:/work/polymarket-trader
pnpm test:run
```

Expected:
- @pmt/engine: 166 tests (160 original + 6 new tables)
- @pmt/llm: 1 smoke
- @pmt/main: 5 tests (4 secrets + 1 smoke)
- @pmt/renderer: 1 smoke
- **Total: 173 tests passing**

- [ ] **Build all packages**

```bash
pnpm build
```

Expected: 4 dist directories, no errors.

- [ ] **Type-check**

```bash
pnpm typecheck
```

Expected: no errors.

If any of the above fail, do NOT proceed to M2 — fix the regression first.

---

## M2 — LLM Provider Layer (~18 tasks)

Goal: build `@pmt/llm` package with 5 adapters covering 24+ providers, plus a routing layer and 3 agent runners that replace the engine's analyzer-client stub.

### Task M2.1: Define core types in `packages/llm/src/types.ts`

**Files:**
- Create: `packages/llm/src/types.ts`
- Create: `packages/llm/tests/types.test.ts`

- [ ] **Step 1: Failing test (verifies type exports)**

`packages/llm/tests/types.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import type {
  AgentId,
  ProviderId,
  AuthType,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ChatChunk,
  LlmProvider,
  ProviderModelInfo,
} from "../src/types.js";

describe("@pmt/llm types", () => {
  it("AgentId enum literals", () => {
    const a: AgentId = "analyzer";
    const r: AgentId = "reviewer";
    const m: AgentId = "risk_manager";
    expect([a, r, m]).toEqual(["analyzer", "reviewer", "risk_manager"]);
  });

  it("ChatMessage shape", () => {
    const msg: ChatMessage = {
      role: "user",
      content: "hi",
    };
    expect(msg.role).toBe("user");
  });

  it("ChatResponse shape", () => {
    const resp: ChatResponse = {
      content: "hello back",
      modelUsed: "claude-opus-4-6",
      providerUsed: "anthropic",
      tokensInput: 10,
      tokensOutput: 5,
      finishReason: "stop",
    };
    expect(resp.tokensInput).toBe(10);
  });
});
```

- [ ] **Step 2: Run, verify fails**

```bash
pnpm --filter @pmt/llm test:run tests/types.test.ts
```

Expected: import error.

- [ ] **Step 3: Implement `packages/llm/src/types.ts`**

```typescript
export type AgentId = "analyzer" | "reviewer" | "risk_manager";

export type ProviderId =
  // OpenAI-compatible API key providers
  | "anthropic_api"
  | "openai"
  | "deepseek"
  | "zhipu"
  | "moonshot"
  | "qwen"
  | "groq"
  | "mistral"
  | "xai"
  | "openrouter"
  | "minimax"
  | "venice"
  | "xiaomi_mimo"
  | "volcengine"
  | "nvidia_nim"
  // Subscription / Coding plans
  | "anthropic_subscription"
  | "gemini_oauth"
  | "zhipu_coding"
  | "qwen_coding"
  | "kimi_code"
  | "minimax_coding"
  | "volcengine_coding"
  | "gemini_api"
  // AWS
  | "bedrock"
  // Local
  | "ollama";

export type AuthType = "api_key" | "oauth" | "cli_credential" | "aws";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  model: string;
  maxTokens?: number;
  temperature?: number;
  stop?: string[];
  /** Stream tokens as they arrive (caller registers a callback). */
  stream?: boolean;
}

export interface ChatResponse {
  content: string;
  modelUsed: string;
  providerUsed: ProviderId;
  tokensInput: number;
  tokensOutput: number;
  finishReason: "stop" | "length" | "content_filter" | "error";
}

export interface ChatChunk {
  delta: string;
  done: boolean;
  final?: ChatResponse;
}

export interface ProviderModelInfo {
  id: string;
  contextWindow: number;
  inputCostPer1k?: number;
  outputCostPer1k?: number;
}

export interface ProviderConnectionState {
  providerId: ProviderId;
  isConnected: boolean;
  lastError?: string;
  modelsAvailable: ProviderModelInfo[];
  quotaUsed?: number;
  quotaLimit?: number;
  quotaResetsAt?: number;
}

export interface LlmProvider {
  readonly id: ProviderId;
  readonly authType: AuthType;
  readonly displayName: string;

  /** Test connection and refresh model list. */
  connect(): Promise<void>;

  /** Returns false if not connected. */
  isConnected(): boolean;

  /** Returns models the provider currently exposes (after connect()). */
  listModels(): ProviderModelInfo[];

  /** Synchronous chat — waits for the full response. */
  chat(request: ChatRequest): Promise<ChatResponse>;

  /** Streaming chat — yields chunks as the LLM generates them. */
  streamChat(request: ChatRequest): AsyncIterable<ChatChunk>;
}

export class ProviderError extends Error {
  constructor(
    public readonly providerId: ProviderId,
    message: string,
    public readonly cause?: unknown
  ) {
    super(`[${providerId}] ${message}`);
    this.name = "ProviderError";
  }
}
```

- [ ] **Step 4: Run, verify pass**

```bash
pnpm --filter @pmt/llm test:run tests/types.test.ts
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/types.ts packages/llm/tests/types.test.ts
git commit -m "feat(llm): define core types (AgentId, ProviderId, ChatRequest, LlmProvider)"
```

### Task M2.2: OpenAI-compatible adapter base class

The single biggest leverage point — this base covers 19 providers. All Chinese coding plans, OpenAI itself, DeepSeek, Zhipu, Moonshot, Qwen, etc. use OpenAI-compatible REST. Differences are: base URL, default models, slight header tweaks.

**Files:**
- Create: `packages/llm/src/adapters/openai-compat.ts`
- Create: `packages/llm/tests/adapters/openai-compat.test.ts`

- [ ] **Step 1: Failing test using mocked fetch**

`packages/llm/tests/adapters/openai-compat.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createOpenAICompatProvider,
  type OpenAICompatConfig,
} from "../../src/adapters/openai-compat.js";

const baseConfig: OpenAICompatConfig = {
  providerId: "deepseek",
  displayName: "DeepSeek",
  apiKey: "sk-test-1234",
  baseUrl: "https://api.deepseek.com/v1",
  defaultModels: [
    { id: "deepseek-chat", contextWindow: 128000 },
    { id: "deepseek-reasoner", contextWindow: 128000 },
  ],
};

describe("openai-compat adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("connects successfully when base URL is reachable", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          data: [
            { id: "deepseek-chat" },
            { id: "deepseek-reasoner" },
          ],
        }),
        { status: 200 }
      )
    );
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels()).toHaveLength(2);
  });

  it("falls back to defaultModels if /models endpoint fails", async () => {
    fetchSpy.mockResolvedValueOnce(new Response("Not Found", { status: 404 }));
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels().map((m) => m.id)).toContain("deepseek-chat");
  });

  it("sends Authorization header on chat", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [{ id: "deepseek-chat" }] }), { status: 200 })
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          choices: [
            {
              message: { role: "assistant", content: "Hello there!" },
              finish_reason: "stop",
            },
          ],
          usage: { prompt_tokens: 5, completion_tokens: 3 },
          model: "deepseek-chat",
        }),
        { status: 200 }
      )
    );
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "deepseek-chat",
    });
    expect(resp.content).toBe("Hello there!");
    expect(resp.tokensInput).toBe(5);
    expect(resp.tokensOutput).toBe(3);
    expect(resp.providerUsed).toBe("deepseek");
    const lastCall = fetchSpy.mock.calls.at(-1);
    expect(lastCall?.[1]?.headers).toMatchObject({ Authorization: "Bearer sk-test-1234" });
  });

  it("throws ProviderError on HTTP 401", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ data: [] }), { status: 200 })
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { message: "Invalid API key" } }), {
        status: 401,
      })
    );
    const provider = createOpenAICompatProvider(baseConfig);
    await provider.connect();
    await expect(
      provider.chat({ messages: [{ role: "user", content: "x" }], model: "deepseek-chat" })
    ).rejects.toThrow(/401/);
  });
});
```

- [ ] **Step 2: Run, verify fails**

```bash
pnpm --filter @pmt/llm test:run tests/adapters/openai-compat.test.ts
```

- [ ] **Step 3: Implement `packages/llm/src/adapters/openai-compat.ts`**

```typescript
import type {
  ChatChunk,
  ChatRequest,
  ChatResponse,
  LlmProvider,
  ProviderId,
  ProviderModelInfo,
} from "../types.js";
import { ProviderError } from "../types.js";

export interface OpenAICompatConfig {
  providerId: ProviderId;
  displayName: string;
  apiKey: string;
  baseUrl: string;
  defaultModels: ProviderModelInfo[];
  /** Optional extra headers (e.g., OpenRouter wants HTTP-Referer). */
  extraHeaders?: Record<string, string>;
  /** Override request timeout in ms (default 30000). */
  timeoutMs?: number;
}

interface OpenAIModelsResponse {
  data: Array<{ id: string }>;
}

interface OpenAIChatResponse {
  choices: Array<{
    message: { role: string; content: string };
    finish_reason: string;
  }>;
  usage?: { prompt_tokens: number; completion_tokens: number };
  model?: string;
}

export function createOpenAICompatProvider(config: OpenAICompatConfig): LlmProvider {
  let connected = false;
  let models: ProviderModelInfo[] = [];

  function buildHeaders(): Record<string, string> {
    return {
      Authorization: `Bearer ${config.apiKey}`,
      "Content-Type": "application/json",
      ...(config.extraHeaders ?? {}),
    };
  }

  async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs ?? 30000);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  return {
    id: config.providerId,
    authType: "api_key",
    displayName: config.displayName,

    async connect() {
      try {
        const resp = await fetchWithTimeout(`${config.baseUrl}/models`, {
          method: "GET",
          headers: buildHeaders(),
        });
        if (resp.ok) {
          const json = (await resp.json()) as OpenAIModelsResponse;
          models = json.data.map((m) => ({ id: m.id, contextWindow: 0 }));
        } else {
          // Endpoint not supported by this provider — use defaults
          models = config.defaultModels;
        }
      } catch {
        models = config.defaultModels;
      }
      connected = true;
    },

    isConnected() {
      return connected;
    },

    listModels() {
      return models.length > 0 ? models : config.defaultModels;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      if (!connected) {
        throw new ProviderError(config.providerId, "not connected — call connect() first");
      }
      const body = {
        model: request.model,
        messages: request.messages,
        max_tokens: request.maxTokens,
        temperature: request.temperature ?? 0.7,
        stop: request.stop,
        stream: false,
      };
      let resp: Response;
      try {
        resp = await fetchWithTimeout(`${config.baseUrl}/chat/completions`, {
          method: "POST",
          headers: buildHeaders(),
          body: JSON.stringify(body),
        });
      } catch (err) {
        throw new ProviderError(config.providerId, "network error", err);
      }
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(
          config.providerId,
          `HTTP ${resp.status}: ${text.slice(0, 200)}`
        );
      }
      const json = (await resp.json()) as OpenAIChatResponse;
      const choice = json.choices[0];
      if (!choice) {
        throw new ProviderError(config.providerId, "empty choices array");
      }
      return {
        content: choice.message.content,
        modelUsed: json.model ?? request.model,
        providerUsed: config.providerId,
        tokensInput: json.usage?.prompt_tokens ?? 0,
        tokensOutput: json.usage?.completion_tokens ?? 0,
        finishReason: mapFinishReason(choice.finish_reason),
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      if (!connected) {
        throw new ProviderError(config.providerId, "not connected — call connect() first");
      }
      const body = {
        model: request.model,
        messages: request.messages,
        max_tokens: request.maxTokens,
        temperature: request.temperature ?? 0.7,
        stream: true,
      };
      const resp = await fetchWithTimeout(`${config.baseUrl}/chat/completions`, {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError(config.providerId, `HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let tokensIn = 0;
      let tokensOut = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;
          try {
            const obj = JSON.parse(payload);
            const delta = obj.choices?.[0]?.delta?.content ?? "";
            if (delta) {
              fullContent += delta;
              yield { delta, done: false };
            }
            if (obj.usage) {
              tokensIn = obj.usage.prompt_tokens ?? 0;
              tokensOut = obj.usage.completion_tokens ?? 0;
            }
          } catch {
            // ignore malformed chunks
          }
        }
      }
      yield {
        delta: "",
        done: true,
        final: {
          content: fullContent,
          modelUsed: request.model,
          providerUsed: config.providerId,
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}

function mapFinishReason(reason: string): ChatResponse["finishReason"] {
  switch (reason) {
    case "stop":
    case "stop_sequence":
      return "stop";
    case "length":
      return "length";
    case "content_filter":
      return "content_filter";
    default:
      return "stop";
  }
}
```

- [ ] **Step 4: Run, verify pass**

```bash
pnpm --filter @pmt/llm test:run tests/adapters/openai-compat.test.ts
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/adapters/openai-compat.ts packages/llm/tests/adapters/openai-compat.test.ts
git commit -m "feat(llm): add OpenAI-compatible adapter base (covers 19 providers)"
```

### Task M2.3: Anthropic adapter (API key + Subscription)

**Files:**
- Create: `packages/llm/src/adapters/anthropic.ts`
- Create: `packages/llm/tests/adapters/anthropic.test.ts`

- [ ] **Step 1: Failing test**

`packages/llm/tests/adapters/anthropic.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createAnthropicProvider } from "../../src/adapters/anthropic.js";

describe("anthropic adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("connects with API key and lists default models", async () => {
    const provider = createAnthropicProvider({ mode: "api_key", apiKey: "sk-ant-test" });
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    const models = provider.listModels();
    expect(models.map((m) => m.id)).toContain("claude-opus-4-6");
    expect(models.map((m) => m.id)).toContain("claude-sonnet-4-6");
    expect(models.map((m) => m.id)).toContain("claude-haiku-4-5");
  });

  it("sends x-api-key header for API key mode chat", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          content: [{ type: "text", text: "Hi from Claude" }],
          model: "claude-opus-4-6",
          usage: { input_tokens: 4, output_tokens: 5 },
          stop_reason: "end_turn",
        }),
        { status: 200 }
      )
    );
    const provider = createAnthropicProvider({ mode: "api_key", apiKey: "sk-ant-key" });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "claude-opus-4-6",
    });
    expect(resp.content).toBe("Hi from Claude");
    expect(resp.tokensInput).toBe(4);
    expect(resp.tokensOutput).toBe(5);
    expect(resp.providerUsed).toBe("anthropic_api");
    const headers = fetchSpy.mock.calls.at(-1)?.[1]?.headers as Record<string, string>;
    expect(headers["x-api-key"]).toBe("sk-ant-key");
    expect(headers["anthropic-version"]).toBeDefined();
  });

  it("subscription mode reads token from cli credentials provider", async () => {
    let credentialCallCount = 0;
    const provider = createAnthropicProvider({
      mode: "subscription",
      readCliToken: async () => {
        credentialCallCount++;
        return "claude-cli-token-xyz";
      },
    });
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          content: [{ type: "text", text: "via subscription" }],
          model: "claude-opus-4-6",
          usage: { input_tokens: 1, output_tokens: 1 },
          stop_reason: "end_turn",
        }),
        { status: 200 }
      )
    );
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "test" }],
      model: "claude-opus-4-6",
    });
    expect(resp.providerUsed).toBe("anthropic_subscription");
    expect(credentialCallCount).toBeGreaterThan(0);
  });

  it("throws on missing API key", () => {
    expect(() => createAnthropicProvider({ mode: "api_key", apiKey: "" })).toThrow(/api key/i);
  });
});
```

- [ ] **Step 2: Run, verify fails**

- [ ] **Step 3: Implement `packages/llm/src/adapters/anthropic.ts`**

```typescript
import type {
  ChatChunk,
  ChatRequest,
  ChatResponse,
  LlmProvider,
  ProviderModelInfo,
} from "../types.js";
import { ProviderError } from "../types.js";

const ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1";
const ANTHROPIC_VERSION = "2023-06-01";

const DEFAULT_MODELS: ProviderModelInfo[] = [
  { id: "claude-opus-4-6", contextWindow: 200000, inputCostPer1k: 0.015, outputCostPer1k: 0.075 },
  { id: "claude-sonnet-4-6", contextWindow: 200000, inputCostPer1k: 0.003, outputCostPer1k: 0.015 },
  { id: "claude-haiku-4-5", contextWindow: 200000, inputCostPer1k: 0.0008, outputCostPer1k: 0.004 },
];

export type AnthropicConfig =
  | { mode: "api_key"; apiKey: string; timeoutMs?: number }
  | {
      mode: "subscription";
      readCliToken: () => Promise<string>;
      timeoutMs?: number;
    };

interface AnthropicChatResponse {
  content: Array<{ type: string; text: string }>;
  model: string;
  usage: { input_tokens: number; output_tokens: number };
  stop_reason: string;
}

export function createAnthropicProvider(config: AnthropicConfig): LlmProvider {
  if (config.mode === "api_key" && !config.apiKey) {
    throw new Error("anthropic adapter: api key is required");
  }
  let connected = false;

  async function getAuthHeaders(): Promise<Record<string, string>> {
    const base: Record<string, string> = {
      "anthropic-version": ANTHROPIC_VERSION,
      "Content-Type": "application/json",
    };
    if (config.mode === "api_key") {
      base["x-api-key"] = config.apiKey;
    } else {
      const token = await config.readCliToken();
      base["Authorization"] = `Bearer ${token}`;
    }
    return base;
  }

  async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs ?? 30000);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  const providerId = config.mode === "api_key" ? "anthropic_api" : "anthropic_subscription";

  return {
    id: providerId,
    authType: config.mode === "api_key" ? "api_key" : "cli_credential",
    displayName: config.mode === "api_key" ? "Anthropic API" : "Anthropic Subscription",

    async connect() {
      // Anthropic doesn't expose a /models endpoint publicly — we always
      // serve the default model list. Connection check is implicit on first chat.
      connected = true;
    },

    isConnected() {
      return connected;
    },

    listModels() {
      return DEFAULT_MODELS;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      const headers = await getAuthHeaders();
      // Anthropic chat API uses a different message format than OpenAI:
      // 'system' messages go to a top-level field, others stay in messages.
      const systemMessages = request.messages.filter((m) => m.role === "system");
      const otherMessages = request.messages.filter((m) => m.role !== "system");
      const body = {
        model: request.model,
        max_tokens: request.maxTokens ?? 4096,
        temperature: request.temperature ?? 0.7,
        system: systemMessages.map((m) => m.content).join("\n\n") || undefined,
        messages: otherMessages.map((m) => ({ role: m.role, content: m.content })),
        stop_sequences: request.stop,
      };
      const resp = await fetchWithTimeout(`${ANTHROPIC_BASE_URL}/messages`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(providerId, `HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      const json = (await resp.json()) as AnthropicChatResponse;
      const text = json.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("");
      return {
        content: text,
        modelUsed: json.model,
        providerUsed: providerId,
        tokensInput: json.usage.input_tokens,
        tokensOutput: json.usage.output_tokens,
        finishReason: json.stop_reason === "end_turn" ? "stop" : "length",
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      const headers = await getAuthHeaders();
      const systemMessages = request.messages.filter((m) => m.role === "system");
      const otherMessages = request.messages.filter((m) => m.role !== "system");
      const body = {
        model: request.model,
        max_tokens: request.maxTokens ?? 4096,
        system: systemMessages.map((m) => m.content).join("\n\n") || undefined,
        messages: otherMessages.map((m) => ({ role: m.role, content: m.content })),
        stream: true,
      };
      const resp = await fetchWithTimeout(`${ANTHROPIC_BASE_URL}/messages`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError(providerId, `HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let tokensIn = 0;
      let tokensOut = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (!payload) continue;
          try {
            const obj = JSON.parse(payload);
            if (obj.type === "content_block_delta" && obj.delta?.text) {
              fullContent += obj.delta.text;
              yield { delta: obj.delta.text, done: false };
            }
            if (obj.type === "message_delta" && obj.usage) {
              tokensOut = obj.usage.output_tokens ?? tokensOut;
            }
            if (obj.type === "message_start" && obj.message?.usage) {
              tokensIn = obj.message.usage.input_tokens ?? 0;
            }
          } catch {
            // ignore malformed events
          }
        }
      }
      yield {
        delta: "",
        done: true,
        final: {
          content: fullContent,
          modelUsed: request.model,
          providerUsed: providerId,
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}
```

- [ ] **Step 4: Run, verify pass**

```bash
pnpm --filter @pmt/llm test:run tests/adapters/anthropic.test.ts
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add packages/llm/src/adapters/anthropic.ts packages/llm/tests/adapters/anthropic.test.ts
git commit -m "feat(llm): add Anthropic adapter (API key + Subscription via CLI token)"
```

### Task M2.4: Gemini adapter (API key + OAuth placeholder)

**Files:**
- Create: `packages/llm/src/adapters/gemini.ts`
- Create: `packages/llm/tests/adapters/gemini.test.ts`

Implement following the same pattern as `openai-compat.ts` but using Google's Generative Language API endpoint and request format. Both `mode: "api_key"` and `mode: "oauth"` initially share the same fetch path; the OAuth token acquisition itself happens in the main process and is handed to the adapter via a `getAccessToken()` callback (similar to Anthropic subscription).

- [ ] **Step 1: Failing test**

`packages/llm/tests/adapters/gemini.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createGeminiProvider } from "../../src/adapters/gemini.js";

describe("gemini adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("api key mode: connects and lists default models", async () => {
    const provider = createGeminiProvider({ mode: "api_key", apiKey: "AIza-test" });
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels().map((m) => m.id)).toContain("gemini-2.5-pro");
    expect(provider.listModels().map((m) => m.id)).toContain("gemini-2.5-flash");
  });

  it("api key mode: appends key as query param", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          candidates: [
            {
              content: { parts: [{ text: "Gemini reply" }] },
              finishReason: "STOP",
            },
          ],
          usageMetadata: { promptTokenCount: 6, candidatesTokenCount: 4 },
        }),
        { status: 200 }
      )
    );
    const provider = createGeminiProvider({ mode: "api_key", apiKey: "AIza-key-123" });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "gemini-2.5-flash",
    });
    expect(resp.content).toBe("Gemini reply");
    expect(resp.tokensInput).toBe(6);
    expect(resp.tokensOutput).toBe(4);
    expect(resp.providerUsed).toBe("gemini_api");
    const url = fetchSpy.mock.calls.at(-1)?.[0] as string;
    expect(url).toContain("key=AIza-key-123");
  });

  it("oauth mode: uses Bearer token", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          candidates: [{ content: { parts: [{ text: "via oauth" }] }, finishReason: "STOP" }],
          usageMetadata: { promptTokenCount: 1, candidatesTokenCount: 1 },
        }),
        { status: 200 }
      )
    );
    const provider = createGeminiProvider({
      mode: "oauth",
      getAccessToken: async () => "ya29.test-oauth-token",
    });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "x" }],
      model: "gemini-2.5-flash",
    });
    expect(resp.providerUsed).toBe("gemini_oauth");
    const headers = fetchSpy.mock.calls.at(-1)?.[1]?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer ya29.test-oauth-token");
  });
});
```

- [ ] **Step 2: Run, verify fails**

- [ ] **Step 3: Implement `packages/llm/src/adapters/gemini.ts`**

```typescript
import type {
  ChatChunk,
  ChatRequest,
  ChatResponse,
  LlmProvider,
  ProviderModelInfo,
} from "../types.js";
import { ProviderError } from "../types.js";

const GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";

const DEFAULT_MODELS: ProviderModelInfo[] = [
  { id: "gemini-2.5-pro", contextWindow: 2_000_000 },
  { id: "gemini-2.5-flash", contextWindow: 1_000_000 },
  { id: "gemini-2.5-flash-lite", contextWindow: 1_000_000 },
];

export type GeminiConfig =
  | { mode: "api_key"; apiKey: string; timeoutMs?: number }
  | { mode: "oauth"; getAccessToken: () => Promise<string>; timeoutMs?: number };

interface GeminiResponse {
  candidates: Array<{
    content: { parts: Array<{ text: string }> };
    finishReason: string;
  }>;
  usageMetadata?: { promptTokenCount: number; candidatesTokenCount: number };
}

export function createGeminiProvider(config: GeminiConfig): LlmProvider {
  let connected = false;
  const providerId = config.mode === "api_key" ? "gemini_api" : "gemini_oauth";

  async function buildUrl(model: string, action: "generateContent" | "streamGenerateContent"): Promise<string> {
    const base = `${GEMINI_BASE_URL}/models/${model}:${action}`;
    if (config.mode === "api_key") {
      return `${base}?key=${encodeURIComponent(config.apiKey)}`;
    }
    return base;
  }

  async function buildHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (config.mode === "oauth") {
      const token = await config.getAccessToken();
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs ?? 30000);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  function buildBody(request: ChatRequest): unknown {
    // Gemini wants user/model alternation; system messages prepended as system_instruction
    const systemText = request.messages
      .filter((m) => m.role === "system")
      .map((m) => m.content)
      .join("\n\n");
    const contents = request.messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role === "assistant" ? "model" : "user",
        parts: [{ text: m.content }],
      }));
    return {
      contents,
      systemInstruction: systemText ? { parts: [{ text: systemText }] } : undefined,
      generationConfig: {
        temperature: request.temperature ?? 0.7,
        maxOutputTokens: request.maxTokens,
        stopSequences: request.stop,
      },
    };
  }

  return {
    id: providerId,
    authType: config.mode === "api_key" ? "api_key" : "oauth",
    displayName: config.mode === "api_key" ? "Gemini API" : "Gemini (Google OAuth)",

    async connect() {
      connected = true;
    },
    isConnected() {
      return connected;
    },
    listModels() {
      return DEFAULT_MODELS;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      const url = await buildUrl(request.model, "generateContent");
      const headers = await buildHeaders();
      const resp = await fetchWithTimeout(url, {
        method: "POST",
        headers,
        body: JSON.stringify(buildBody(request)),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError(providerId, `HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      const json = (await resp.json()) as GeminiResponse;
      const candidate = json.candidates[0];
      if (!candidate) {
        throw new ProviderError(providerId, "empty candidates array");
      }
      const text = candidate.content.parts.map((p) => p.text).join("");
      return {
        content: text,
        modelUsed: request.model,
        providerUsed: providerId,
        tokensInput: json.usageMetadata?.promptTokenCount ?? 0,
        tokensOutput: json.usageMetadata?.candidatesTokenCount ?? 0,
        finishReason: candidate.finishReason === "STOP" ? "stop" : "length",
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      const url = await buildUrl(request.model, "streamGenerateContent");
      const headers = await buildHeaders();
      const resp = await fetchWithTimeout(`${url}${url.includes("?") ? "&" : "?"}alt=sse`, {
        method: "POST",
        headers,
        body: JSON.stringify(buildBody(request)),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError(providerId, `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let tokensIn = 0;
      let tokensOut = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const obj = JSON.parse(line.slice(6)) as GeminiResponse;
            const delta = obj.candidates?.[0]?.content?.parts?.[0]?.text ?? "";
            if (delta) {
              fullContent += delta;
              yield { delta, done: false };
            }
            if (obj.usageMetadata) {
              tokensIn = obj.usageMetadata.promptTokenCount ?? tokensIn;
              tokensOut = obj.usageMetadata.candidatesTokenCount ?? tokensOut;
            }
          } catch {
            // ignore
          }
        }
      }
      yield {
        delta: "",
        done: true,
        final: {
          content: fullContent,
          modelUsed: request.model,
          providerUsed: providerId,
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}
```

- [ ] **Step 4: Run, verify pass + commit**

```bash
pnpm --filter @pmt/llm test:run tests/adapters/gemini.test.ts
git add packages/llm/src/adapters/gemini.ts packages/llm/tests/adapters/gemini.test.ts
git commit -m "feat(llm): add Gemini adapter (API key + OAuth)"
```

### Task M2.5: Bedrock adapter and Ollama adapter

These two are simpler and can be done in one task.

**Files:**
- Create: `packages/llm/src/adapters/bedrock.ts`
- Create: `packages/llm/src/adapters/ollama.ts`
- Create: `packages/llm/tests/adapters/bedrock.test.ts`
- Create: `packages/llm/tests/adapters/ollama.test.ts`

- [ ] **Step 1: Bedrock test**

```typescript
import { describe, it, expect } from "vitest";
import { createBedrockProvider } from "../../src/adapters/bedrock.js";

describe("bedrock adapter", () => {
  it("constructs with AWS credentials", () => {
    const provider = createBedrockProvider({
      region: "us-east-1",
      accessKeyId: "AKIA-test",
      secretAccessKey: "secret-test",
    });
    expect(provider.id).toBe("bedrock");
    expect(provider.authType).toBe("aws");
  });

  it("lists default Bedrock models", async () => {
    const provider = createBedrockProvider({
      region: "us-east-1",
      accessKeyId: "x",
      secretAccessKey: "y",
    });
    await provider.connect();
    expect(provider.listModels().map((m) => m.id)).toContain("anthropic.claude-opus-4-v1:0");
  });
});
```

- [ ] **Step 2: Bedrock implementation**

```typescript
import type { ChatChunk, ChatRequest, ChatResponse, LlmProvider, ProviderModelInfo } from "../types.js";
import { ProviderError } from "../types.js";

const DEFAULT_MODELS: ProviderModelInfo[] = [
  { id: "anthropic.claude-opus-4-v1:0", contextWindow: 200000 },
  { id: "anthropic.claude-sonnet-4-v1:0", contextWindow: 200000 },
  { id: "meta.llama3-70b-instruct-v1:0", contextWindow: 8192 },
];

export interface BedrockConfig {
  region: string;
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
}

export function createBedrockProvider(config: BedrockConfig): LlmProvider {
  let connected = false;

  return {
    id: "bedrock",
    authType: "aws",
    displayName: "AWS Bedrock",

    async connect() {
      // Real implementation: use @aws-sdk/client-bedrock-runtime to list models
      // For v1 we just mark connected and return defaults
      connected = true;
    },
    isConnected() {
      return connected;
    },
    listModels() {
      return DEFAULT_MODELS;
    },
    async chat(_request: ChatRequest): Promise<ChatResponse> {
      throw new ProviderError(
        "bedrock",
        "Bedrock chat not yet implemented — install @aws-sdk/client-bedrock-runtime and complete in a follow-up task"
      );
    },
    async *streamChat(_request: ChatRequest): AsyncIterable<ChatChunk> {
      throw new ProviderError("bedrock", "Bedrock streamChat not yet implemented");
    },
  };
}
```

This is a deliberate stub. Bedrock requires AWS SDK signatures which are non-trivial. M2 ships a connect-only stub; full chat implementation is deferred to a follow-up task once user demonstrates need (YAGNI).

- [ ] **Step 3: Ollama test**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createOllamaProvider } from "../../src/adapters/ollama.js";

describe("ollama adapter", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("connects to localhost and discovers models", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          models: [
            { name: "qwen2.5:32b" },
            { name: "deepseek-r1:14b" },
          ],
        }),
        { status: 200 }
      )
    );
    const provider = createOllamaProvider({ baseUrl: "http://localhost:11434" });
    await provider.connect();
    expect(provider.isConnected()).toBe(true);
    expect(provider.listModels().map((m) => m.id)).toEqual(["qwen2.5:32b", "deepseek-r1:14b"]);
  });

  it("chat returns content", async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ models: [{ name: "qwen2.5:32b" }] }), { status: 200 })
    );
    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          message: { role: "assistant", content: "Local model says hi" },
          model: "qwen2.5:32b",
          prompt_eval_count: 3,
          eval_count: 8,
          done_reason: "stop",
        }),
        { status: 200 }
      )
    );
    const provider = createOllamaProvider({ baseUrl: "http://localhost:11434" });
    await provider.connect();
    const resp = await provider.chat({
      messages: [{ role: "user", content: "hi" }],
      model: "qwen2.5:32b",
    });
    expect(resp.content).toBe("Local model says hi");
    expect(resp.tokensInput).toBe(3);
    expect(resp.tokensOutput).toBe(8);
  });
});
```

- [ ] **Step 4: Ollama implementation**

```typescript
import type { ChatChunk, ChatRequest, ChatResponse, LlmProvider, ProviderModelInfo } from "../types.js";
import { ProviderError } from "../types.js";

export interface OllamaConfig {
  baseUrl: string;
  timeoutMs?: number;
}

interface OllamaListResponse {
  models: Array<{ name: string }>;
}

interface OllamaChatResponse {
  message: { role: string; content: string };
  model: string;
  prompt_eval_count?: number;
  eval_count?: number;
  done_reason?: string;
}

export function createOllamaProvider(config: OllamaConfig): LlmProvider {
  let connected = false;
  let models: ProviderModelInfo[] = [];

  async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), config.timeoutMs ?? 60000);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  return {
    id: "ollama",
    authType: "api_key",
    displayName: "Ollama (local)",

    async connect() {
      const resp = await fetchWithTimeout(`${config.baseUrl}/api/tags`, { method: "GET" });
      if (!resp.ok) {
        throw new ProviderError("ollama", `failed to reach Ollama at ${config.baseUrl}: HTTP ${resp.status}`);
      }
      const json = (await resp.json()) as OllamaListResponse;
      models = json.models.map((m) => ({ id: m.name, contextWindow: 8192 }));
      connected = true;
    },

    isConnected() {
      return connected;
    },

    listModels() {
      return models;
    },

    async chat(request: ChatRequest): Promise<ChatResponse> {
      if (!connected) throw new ProviderError("ollama", "not connected");
      const body = {
        model: request.model,
        messages: request.messages,
        stream: false,
        options: {
          temperature: request.temperature ?? 0.7,
          num_predict: request.maxTokens,
        },
      };
      const resp = await fetchWithTimeout(`${config.baseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        throw new ProviderError("ollama", `HTTP ${resp.status}: ${text}`);
      }
      const json = (await resp.json()) as OllamaChatResponse;
      return {
        content: json.message.content,
        modelUsed: json.model,
        providerUsed: "ollama",
        tokensInput: json.prompt_eval_count ?? 0,
        tokensOutput: json.eval_count ?? 0,
        finishReason: json.done_reason === "stop" ? "stop" : "length",
      };
    },

    async *streamChat(request: ChatRequest): AsyncIterable<ChatChunk> {
      if (!connected) throw new ProviderError("ollama", "not connected");
      const body = {
        model: request.model,
        messages: request.messages,
        stream: true,
      };
      const resp = await fetchWithTimeout(`${config.baseUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        throw new ProviderError("ollama", `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let tokensIn = 0;
      let tokensOut = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const obj = JSON.parse(line);
            const delta = obj.message?.content ?? "";
            if (delta) {
              fullContent += delta;
              yield { delta, done: false };
            }
            if (obj.done) {
              tokensIn = obj.prompt_eval_count ?? 0;
              tokensOut = obj.eval_count ?? 0;
            }
          } catch {
            // ignore
          }
        }
      }
      yield {
        delta: "",
        done: true,
        final: {
          content: fullContent,
          modelUsed: request.model,
          providerUsed: "ollama",
          tokensInput: tokensIn,
          tokensOutput: tokensOut,
          finishReason: "stop",
        },
      };
    },
  };
}
```

- [ ] **Step 5: Run both adapter tests, verify pass**

```bash
pnpm --filter @pmt/llm test:run tests/adapters/bedrock.test.ts tests/adapters/ollama.test.ts
```

Expected: Bedrock 2 + Ollama 2 = 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add packages/llm/src/adapters/bedrock.ts packages/llm/src/adapters/ollama.ts packages/llm/tests/adapters/bedrock.test.ts packages/llm/tests/adapters/ollama.test.ts
git commit -m "feat(llm): add Bedrock (stub) and Ollama adapters"
```

### Task M2.6: Provider registry + per-agent assignment

The registry holds the user's configured providers and tracks which provider/model each of the 3 agents is currently using.

**Files:**
- Create: `packages/llm/src/registry.ts`
- Create: `packages/llm/tests/registry.test.ts`

- [ ] **Step 1: Failing test**

```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { createProviderRegistry } from "../src/registry.js";
import type { LlmProvider } from "../src/types.js";

function makeFakeProvider(id: string): LlmProvider {
  return {
    id: id as any,
    authType: "api_key",
    displayName: id,
    connect: vi.fn().mockResolvedValue(undefined),
    isConnected: () => true,
    listModels: () => [{ id: "model-a", contextWindow: 1000 }],
    chat: vi.fn(),
    streamChat: vi.fn() as any,
  };
}

describe("providerRegistry", () => {
  let registry: ReturnType<typeof createProviderRegistry>;

  beforeEach(() => {
    registry = createProviderRegistry();
  });

  it("registers and retrieves a provider", () => {
    const provider = makeFakeProvider("anthropic_api");
    registry.register(provider);
    expect(registry.get("anthropic_api")).toBe(provider);
  });

  it("listConnected returns only connected providers", () => {
    const a = makeFakeProvider("anthropic_api");
    const b = { ...makeFakeProvider("openai"), isConnected: () => false };
    registry.register(a);
    registry.register(b as any);
    expect(registry.listConnected()).toHaveLength(1);
    expect(registry.listConnected()[0]?.id).toBe("anthropic_api");
  });

  it("assignAgentModel sets a provider+model for an agent", () => {
    const provider = makeFakeProvider("anthropic_api");
    registry.register(provider);
    registry.assignAgentModel("analyzer", "anthropic_api", "model-a");
    const assignment = registry.getAgentAssignment("analyzer");
    expect(assignment?.providerId).toBe("anthropic_api");
    expect(assignment?.modelId).toBe("model-a");
  });

  it("getProviderForAgent returns the registered provider", () => {
    const provider = makeFakeProvider("anthropic_api");
    registry.register(provider);
    registry.assignAgentModel("analyzer", "anthropic_api", "model-a");
    const result = registry.getProviderForAgent("analyzer");
    expect(result?.provider.id).toBe("anthropic_api");
    expect(result?.modelId).toBe("model-a");
  });

  it("getProviderForAgent returns null if no assignment", () => {
    expect(registry.getProviderForAgent("analyzer")).toBeNull();
  });
});
```

- [ ] **Step 2: Implement `packages/llm/src/registry.ts`**

```typescript
import type { AgentId, LlmProvider, ProviderId } from "./types.js";

export interface AgentAssignment {
  providerId: ProviderId;
  modelId: string;
}

export interface ProviderRegistry {
  register(provider: LlmProvider): void;
  unregister(providerId: ProviderId): void;
  get(providerId: ProviderId): LlmProvider | undefined;
  list(): LlmProvider[];
  listConnected(): LlmProvider[];

  assignAgentModel(agentId: AgentId, providerId: ProviderId, modelId: string): void;
  getAgentAssignment(agentId: AgentId): AgentAssignment | undefined;
  getProviderForAgent(agentId: AgentId): { provider: LlmProvider; modelId: string } | null;
}

export function createProviderRegistry(): ProviderRegistry {
  const providers = new Map<ProviderId, LlmProvider>();
  const assignments = new Map<AgentId, AgentAssignment>();

  return {
    register(provider) {
      providers.set(provider.id, provider);
    },
    unregister(providerId) {
      providers.delete(providerId);
      // Remove any agent assignments pointing at this provider
      for (const [agentId, assignment] of assignments.entries()) {
        if (assignment.providerId === providerId) {
          assignments.delete(agentId);
        }
      }
    },
    get(providerId) {
      return providers.get(providerId);
    },
    list() {
      return Array.from(providers.values());
    },
    listConnected() {
      return Array.from(providers.values()).filter((p) => p.isConnected());
    },
    assignAgentModel(agentId, providerId, modelId) {
      if (!providers.has(providerId)) {
        throw new Error(`registry.assignAgentModel: provider ${providerId} not registered`);
      }
      assignments.set(agentId, { providerId, modelId });
    },
    getAgentAssignment(agentId) {
      return assignments.get(agentId);
    },
    getProviderForAgent(agentId) {
      const assignment = assignments.get(agentId);
      if (!assignment) return null;
      const provider = providers.get(assignment.providerId);
      if (!provider) return null;
      return { provider, modelId: assignment.modelId };
    },
  };
}
```

- [ ] **Step 3: Run, verify pass + commit**

```bash
pnpm --filter @pmt/llm test:run tests/registry.test.ts
git add packages/llm/src/registry.ts packages/llm/tests/registry.test.ts
git commit -m "feat(llm): add provider registry with per-agent model assignment"
```

### Task M2.7: Routing strategy "Prefer Subscription"

When an agent's selected model is available via both a Subscription (free / no cost) and an API key (paid), the router prefers the subscription. If subscription quota is exhausted, fall back to the API key provider with the same model.

**Files:**
- Create: `packages/llm/src/routing.ts`
- Create: `packages/llm/tests/routing.test.ts`

- [ ] **Step 1: Failing test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { resolveProviderForModel } from "../src/routing.js";
import type { LlmProvider } from "../src/types.js";

function makeProvider(id: string, models: string[], authType: "api_key" | "cli_credential" | "oauth"): LlmProvider {
  return {
    id: id as any,
    authType,
    displayName: id,
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => models.map((m) => ({ id: m, contextWindow: 1000 })),
    chat: vi.fn(),
    streamChat: vi.fn() as any,
  };
}

describe("resolveProviderForModel (Prefer Subscription)", () => {
  it("prefers cli_credential subscription over api_key when both have model", () => {
    const sub = makeProvider("anthropic_subscription", ["claude-opus-4-6"], "cli_credential");
    const api = makeProvider("anthropic_api", ["claude-opus-4-6"], "api_key");
    const result = resolveProviderForModel("claude-opus-4-6", [sub, api]);
    expect(result?.id).toBe("anthropic_subscription");
  });

  it("prefers oauth (free tier) over api_key when both have model", () => {
    const oauth = makeProvider("gemini_oauth", ["gemini-2.5-flash"], "oauth");
    const api = makeProvider("gemini_api", ["gemini-2.5-flash"], "api_key");
    const result = resolveProviderForModel("gemini-2.5-flash", [oauth, api]);
    expect(result?.id).toBe("gemini_oauth");
  });

  it("falls back to api_key if no subscription available", () => {
    const api = makeProvider("openai", ["gpt-5"], "api_key");
    const result = resolveProviderForModel("gpt-5", [api]);
    expect(result?.id).toBe("openai");
  });

  it("returns null if no provider has the model", () => {
    const api = makeProvider("openai", ["gpt-5"], "api_key");
    expect(resolveProviderForModel("claude-opus-4-6", [api])).toBeNull();
  });
});
```

- [ ] **Step 2: Implement `packages/llm/src/routing.ts`**

```typescript
import type { LlmProvider } from "./types.js";

/**
 * Routing strategy: "Prefer Subscription".
 *
 * Given a desired model and the list of currently-connected providers,
 * pick the best provider in this priority order:
 *   1. Subscription (cli_credential)
 *   2. OAuth (free tier)
 *   3. AWS (Bedrock — paid but counted separately from per-token API)
 *   4. API key (paid per token)
 *
 * Returns null if no connected provider exposes the model.
 */
const PRIORITY_ORDER: Record<LlmProvider["authType"], number> = {
  cli_credential: 0,
  oauth: 1,
  aws: 2,
  api_key: 3,
};

export function resolveProviderForModel(
  modelId: string,
  providers: LlmProvider[]
): LlmProvider | null {
  const candidates = providers.filter((p) =>
    p.listModels().some((m) => m.id === modelId)
  );
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => PRIORITY_ORDER[a.authType] - PRIORITY_ORDER[b.authType]);
  return candidates[0] ?? null;
}
```

- [ ] **Step 3: Run, verify pass + commit**

```bash
pnpm --filter @pmt/llm test:run tests/routing.test.ts
git add packages/llm/src/routing.ts packages/llm/tests/routing.test.ts
git commit -m "feat(llm): add Prefer Subscription routing strategy"
```

### Task M2.8: Analyzer runner — replaces engine's stub

This is the critical replacement: the engine's `analyzer-client.ts` was a stub that throws. The new `analyzer-runner.ts` calls the LLM via the registry and returns a parsed verdict ready for the executor.

**Files:**
- Create: `packages/llm/src/runners/personas/analyzer.ts`
- Create: `packages/llm/src/runners/analyzer-runner.ts`
- Create: `packages/llm/tests/runners/analyzer-runner.test.ts`

- [ ] **Step 1: Failing test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { createAnalyzerRunner } from "../../src/runners/analyzer-runner.js";
import type { LlmProvider } from "../../src/types.js";

function makeProvider(replyContent: string): LlmProvider {
  return {
    id: "anthropic_api" as any,
    authType: "api_key",
    displayName: "Test",
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => [{ id: "test-model", contextWindow: 100000 }],
    chat: vi.fn().mockResolvedValue({
      content: replyContent,
      modelUsed: "test-model",
      providerUsed: "anthropic_api",
      tokensInput: 100,
      tokensOutput: 50,
      finishReason: "stop",
    }),
    streamChat: vi.fn() as any,
  };
}

describe("analyzerRunner", () => {
  const sampleTrigger = {
    type: "trigger" as const,
    market_id: "m1",
    market_title: "Will it rain?",
    resolves_at: Date.now() + 7_200_000,
    triggered_at: Date.now(),
    direction: "buy_yes" as const,
    snapshot: {
      volume_1m: 3500,
      net_flow_1m: 3200,
      unique_traders_1m: 4,
      price_move_5m: 0.04,
      liquidity: 6000,
      current_mid_price: 0.55,
    },
  };

  it("parses a real_signal verdict from LLM JSON response", async () => {
    const provider = makeProvider(
      JSON.stringify({
        verdict: "real_signal",
        direction: "buy_yes",
        confidence: 0.8,
        reasoning: "Strong flow",
      })
    );
    const registry = {
      getProviderForAgent: () => ({ provider, modelId: "test-model" }),
    } as any;
    const runner = createAnalyzerRunner({ registry });
    const result = await runner.judge(sampleTrigger);
    expect(result).not.toBeNull();
    expect(result?.verdict).toBe("real_signal");
    expect(result?.confidence).toBe(0.8);
  });

  it("returns null if no provider assigned", async () => {
    const registry = { getProviderForAgent: () => null } as any;
    const runner = createAnalyzerRunner({ registry });
    const result = await runner.judge(sampleTrigger);
    expect(result).toBeNull();
  });

  it("returns null on LLM timeout", async () => {
    const provider = {
      id: "anthropic_api" as any,
      authType: "api_key",
      displayName: "Test",
      connect: vi.fn(),
      isConnected: () => true,
      listModels: () => [{ id: "test-model", contextWindow: 100000 }],
      chat: vi.fn().mockImplementation(() => new Promise(() => {})), // never resolves
      streamChat: vi.fn() as any,
    };
    const registry = {
      getProviderForAgent: () => ({ provider, modelId: "test-model" }),
    } as any;
    const runner = createAnalyzerRunner({ registry, timeoutMs: 50 });
    const result = await runner.judge(sampleTrigger);
    expect(result).toBeNull();
  });

  it("returns null on unparseable LLM output", async () => {
    const provider = makeProvider("This is not JSON");
    const registry = {
      getProviderForAgent: () => ({ provider, modelId: "test-model" }),
    } as any;
    const runner = createAnalyzerRunner({ registry });
    const result = await runner.judge(sampleTrigger);
    expect(result).toBeNull();
  });
});
```

- [ ] **Step 2: Implement `packages/llm/src/runners/personas/analyzer.ts`**

```typescript
export const ANALYZER_SYSTEM_PROMPT = `You are the Polymarket Analyzer, judging a single potential trading signal.

Given a market context, decide whether it is a real actionable signal or noise. Output ONLY a JSON object in this exact schema (no extra text):

{
  "verdict": "real_signal" | "noise" | "uncertain",
  "direction": "buy_yes" | "buy_no",
  "confidence": 0.0 to 1.0,
  "reasoning": "1-2 sentence justification"
}

Hard constraints:
- Refuse signals where price is in the dead zone [0.60, 0.85] — respond with verdict "noise" and reasoning "in dead zone"
- Do NOT bias confidence upward; report your true confidence
- If the trader cluster looks like a single actor (similar timing, repeated addresses), call it "noise"
`;
```

- [ ] **Step 3: Implement `packages/llm/src/runners/analyzer-runner.ts`**

```typescript
import type { ProviderRegistry } from "../registry.js";
import { ANALYZER_SYSTEM_PROMPT } from "./personas/analyzer.js";

// Re-import types from engine — avoids circular dep by treating these as
// structural types passed in by the caller
export interface TriggerSnapshot {
  volume_1m: number;
  net_flow_1m: number;
  unique_traders_1m: number;
  price_move_5m: number;
  liquidity: number;
  current_mid_price: number;
}

export interface TriggerEvent {
  type: "trigger";
  market_id: string;
  market_title: string;
  resolves_at: number;
  triggered_at: number;
  direction: "buy_yes" | "buy_no";
  snapshot: TriggerSnapshot;
}

export interface ParsedVerdict {
  verdict: "real_signal" | "noise" | "uncertain";
  direction: "buy_yes" | "buy_no";
  confidence: number;
  reasoning: string;
}

export interface AnalyzerRunnerOptions {
  registry: ProviderRegistry;
  timeoutMs?: number;
}

export interface AnalyzerRunner {
  judge(trigger: TriggerEvent): Promise<ParsedVerdict | null>;
}

function buildPrompt(trigger: TriggerEvent): string {
  const ms = trigger.resolves_at - trigger.triggered_at;
  const hours = Math.floor(ms / 3600000);
  const mins = Math.floor((ms % 3600000) / 60000);
  const resolveIn = hours > 0 ? `${hours}h ${mins}m` : `${mins} minutes`;
  return `Market: "${trigger.market_title}"
Market ID: ${trigger.market_id}
Current price: ${trigger.snapshot.current_mid_price.toFixed(4)}
Resolves in: ${resolveIn}
Liquidity: $${trigger.snapshot.liquidity.toFixed(0)}

Detected flow indicators:
- Volume (1m): $${trigger.snapshot.volume_1m.toFixed(0)}
- Net flow (1m): $${trigger.snapshot.net_flow_1m.toFixed(0)} (${trigger.direction === "buy_yes" ? "toward YES" : "toward NO"})
- Unique traders (1m): ${trigger.snapshot.unique_traders_1m}
- Price move (5m): ${(trigger.snapshot.price_move_5m * 100).toFixed(2)}%

Suggested direction from flow: ${trigger.direction}

Respond with ONLY the JSON verdict object.`;
}

function tryParseVerdict(text: string): ParsedVerdict | null {
  // Strip markdown fences if present
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || obj === null) return null;
    const o = obj as Record<string, unknown>;
    if (!["real_signal", "noise", "uncertain"].includes(o.verdict as string)) return null;
    if (!["buy_yes", "buy_no"].includes(o.direction as string)) return null;
    const conf = Number(o.confidence);
    if (!Number.isFinite(conf) || conf < 0 || conf > 1) return null;
    return {
      verdict: o.verdict as ParsedVerdict["verdict"],
      direction: o.direction as ParsedVerdict["direction"],
      confidence: conf,
      reasoning: typeof o.reasoning === "string" ? o.reasoning : "",
    };
  } catch {
    return null;
  }
}

export function createAnalyzerRunner(opts: AnalyzerRunnerOptions): AnalyzerRunner {
  const timeoutMs = opts.timeoutMs ?? 30000;

  return {
    async judge(trigger: TriggerEvent): Promise<ParsedVerdict | null> {
      const assigned = opts.registry.getProviderForAgent("analyzer");
      if (!assigned) return null;

      const prompt = buildPrompt(trigger);
      const chatPromise = assigned.provider.chat({
        model: assigned.modelId,
        messages: [
          { role: "system", content: ANALYZER_SYSTEM_PROMPT },
          { role: "user", content: prompt },
        ],
        temperature: 0.3,
        maxTokens: 500,
      });

      const timeoutPromise = new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), timeoutMs)
      );

      const result = await Promise.race([
        chatPromise.catch(() => null),
        timeoutPromise,
      ]);
      if (!result) return null;
      return tryParseVerdict(result.content);
    },
  };
}
```

- [ ] **Step 4: Run, verify pass + commit**

```bash
pnpm --filter @pmt/llm test:run tests/runners/analyzer-runner.test.ts
git add packages/llm/src/runners/personas/analyzer.ts packages/llm/src/runners/analyzer-runner.ts packages/llm/tests/runners/analyzer-runner.test.ts
git commit -m "feat(llm): add analyzer runner replacing engine stub"
```

### Task M2.9: Reviewer runner

**Files:**
- Create: `packages/llm/src/runners/personas/reviewer.ts`
- Create: `packages/llm/src/runners/reviewer-runner.ts`
- Create: `packages/llm/tests/runners/reviewer-runner.test.ts`

Implement following the same pattern as analyzer-runner. The Reviewer runner takes the engine's `runReviewer` function output (per-bucket statistics, kill switches) and asks the LLM to write a natural-language narrative section that gets appended to the markdown report. It does NOT replace the engine's reviewer.ts — it augments the markdown with LLM commentary.

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { createReviewerRunner } from "../../src/runners/reviewer-runner.js";
import type { LlmProvider } from "../../src/types.js";

function makeProvider(content: string): LlmProvider {
  return {
    id: "anthropic_api" as any,
    authType: "api_key",
    displayName: "test",
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => [{ id: "m", contextWindow: 1000 }],
    chat: vi.fn().mockResolvedValue({
      content,
      modelUsed: "m",
      providerUsed: "anthropic_api",
      tokensInput: 100,
      tokensOutput: 200,
      finishReason: "stop",
    }),
    streamChat: vi.fn() as any,
  };
}

describe("reviewerRunner", () => {
  it("generates narrative commentary for bucket stats", async () => {
    const provider = makeProvider("Strong week. Bucket 0.40-0.45 stood out at 71% win rate.");
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createReviewerRunner({ registry });
    const narrative = await runner.generateCommentary({
      period: "weekly",
      totalPnl7d: 127.50,
      bucketStats: [
        { price_bucket: 0.40, trade_count: 7, win_count: 5, win_rate: 0.714, total_pnl_net_usdc: 56.20 },
        { price_bucket: 0.50, trade_count: 4, win_count: 2, win_rate: 0.5, total_pnl_net_usdc: 15.80 },
      ],
      killSwitches: [],
    });
    expect(narrative).toContain("Strong week");
  });

  it("returns empty string if no provider assigned", async () => {
    const registry = { getProviderForAgent: () => null } as any;
    const runner = createReviewerRunner({ registry });
    const narrative = await runner.generateCommentary({
      period: "daily",
      totalPnl7d: 0,
      bucketStats: [],
      killSwitches: [],
    });
    expect(narrative).toBe("");
  });
});
```

- [ ] **Step 2: Persona at `packages/llm/src/runners/personas/reviewer.ts`**

```typescript
export const REVIEWER_SYSTEM_PROMPT = `You are the Polymarket Reviewer, generating a brief narrative commentary for the daily/weekly trading report.

Given per-bucket performance statistics, write 2-4 short paragraphs covering:
1. Overall performance verdict (was this period a win, loss, or sideways?)
2. The 1-2 standout buckets (best and worst by win rate, with sample size)
3. Patterns worth noting (over-trading, time-stop overuse, particular markets)
4. If there are kill switches, mention them prominently as warnings

Be data-driven, concise, and avoid speculation. If sample sizes are small, say "insufficient data" rather than guessing.

Output plain markdown. No headers — just paragraphs and optional bullet lists.`;
```

- [ ] **Step 3: Implementation `packages/llm/src/runners/reviewer-runner.ts`**

```typescript
import type { ProviderRegistry } from "../registry.js";
import { REVIEWER_SYSTEM_PROMPT } from "./personas/reviewer.js";

export interface BucketStat {
  price_bucket: number;
  trade_count: number;
  win_count: number;
  win_rate: number;
  total_pnl_net_usdc: number;
}

export interface KillSwitchSummary {
  strategy: string;
  reason: string;
}

export interface ReviewerInput {
  period: "daily" | "weekly";
  totalPnl7d: number;
  bucketStats: BucketStat[];
  killSwitches: KillSwitchSummary[];
}

export interface ReviewerRunner {
  generateCommentary(input: ReviewerInput): Promise<string>;
}

function buildPrompt(input: ReviewerInput): string {
  const lines: string[] = [];
  lines.push(`Period: ${input.period}`);
  lines.push(`7-day net PnL: $${input.totalPnl7d.toFixed(2)}`);
  lines.push(``);
  lines.push(`Per-bucket stats:`);
  for (const b of input.bucketStats) {
    lines.push(
      `- bucket ${b.price_bucket.toFixed(2)}: ${b.trade_count} trades, ${b.win_count} wins (${(b.win_rate * 100).toFixed(1)}%), net $${b.total_pnl_net_usdc.toFixed(2)}`
    );
  }
  if (input.killSwitches.length > 0) {
    lines.push(``);
    lines.push(`Kill switches fired:`);
    for (const k of input.killSwitches) {
      lines.push(`- ${k.strategy}: ${k.reason}`);
    }
  }
  return lines.join("\n");
}

export function createReviewerRunner(opts: { registry: ProviderRegistry }): ReviewerRunner {
  return {
    async generateCommentary(input: ReviewerInput): Promise<string> {
      const assigned = opts.registry.getProviderForAgent("reviewer");
      if (!assigned) return "";

      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: REVIEWER_SYSTEM_PROMPT },
            { role: "user", content: buildPrompt(input) },
          ],
          temperature: 0.5,
          maxTokens: 800,
        });
        return resp.content;
      } catch {
        return "";
      }
    },
  };
}
```

- [ ] **Step 4: Run + commit**

```bash
pnpm --filter @pmt/llm test:run tests/runners/reviewer-runner.test.ts
git add packages/llm/src/runners/personas/reviewer.ts packages/llm/src/runners/reviewer-runner.ts packages/llm/tests/runners/reviewer-runner.test.ts
git commit -m "feat(llm): add reviewer runner for narrative commentary"
```

### Task M2.10: Risk Manager / Coordinator runner

The Risk Manager runner has TWO modes: reactive (user-question-driven, called from chat IPC) and proactive (Coordinator, called every hour by the main process scheduler).

**Files:**
- Create: `packages/llm/src/runners/personas/risk-manager.ts`
- Create: `packages/llm/src/runners/risk-mgr-runner.ts`
- Create: `packages/llm/tests/runners/risk-mgr-runner.test.ts`

- [ ] **Step 1: Persona**

```typescript
export const RISK_MANAGER_SYSTEM_PROMPT = `You are the Polymarket Risk Manager / Coordinator — a read-only employee that monitors the trading system's health and answers user questions.

You can read but NOT modify any configuration. If a user asks you to change settings, reply that they need to do it themselves in the Settings page or approve a Reviewer proposal.

In REACTIVE mode (user-asked), answer their question concisely and cite specific numbers from the system state. Use markdown for formatting.

In PROACTIVE mode (hourly Coordinator brief), output a JSON object with this schema:

{
  "summary": "1-2 sentence overall status",
  "alerts": [{"severity": "info|warning|critical", "text": "..."}],
  "suggestions": ["short suggestion 1", "short suggestion 2"]
}

Severity guidelines:
- info: routine observation
- warning: something to watch (e.g., approaching halt threshold, unusual market activity)
- critical: action needed soon (e.g., 90% to daily halt, multiple kill switches firing)`;
```

- [ ] **Step 2: Test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { createRiskMgrRunner } from "../../src/runners/risk-mgr-runner.js";
import type { LlmProvider } from "../../src/types.js";

function makeProvider(content: string): LlmProvider {
  return {
    id: "anthropic_api" as any,
    authType: "api_key",
    displayName: "test",
    connect: vi.fn(),
    isConnected: () => true,
    listModels: () => [{ id: "m", contextWindow: 1000 }],
    chat: vi.fn().mockResolvedValue({
      content,
      modelUsed: "m",
      providerUsed: "anthropic_api",
      tokensInput: 100,
      tokensOutput: 50,
      finishReason: "stop",
    }),
    streamChat: vi.fn() as any,
  };
}

describe("riskMgrRunner reactive mode", () => {
  it("answers user question with system state context", async () => {
    const provider = makeProvider("Currently safe. Daily DD: -0.8%, well under -2.0% halt.");
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createRiskMgrRunner({ registry });
    const reply = await runner.answerQuestion({
      question: "Are we close to any halts?",
      systemState: {
        portfolioState: {
          current_equity: 9920,
          day_start_equity: 10000,
          daily_halt_triggered: false,
        },
        recentTrades: [],
        openPositionCount: 3,
      },
    });
    expect(reply).toContain("safe");
  });
});

describe("riskMgrRunner proactive mode", () => {
  it("returns parsed Coordinator brief JSON", async () => {
    const provider = makeProvider(
      JSON.stringify({
        summary: "Stable hour. 7 triggers, 2 entered.",
        alerts: [{ severity: "info", text: "BTC market activity elevated" }],
        suggestions: ["Consider tightening unique_traders_1m to 4"],
      })
    );
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createRiskMgrRunner({ registry });
    const brief = await runner.generateBrief({
      windowMs: 3600000,
      systemState: {
        portfolioState: {
          current_equity: 10100,
          day_start_equity: 10000,
          daily_halt_triggered: false,
        },
        recentTrades: [],
        openPositionCount: 2,
      },
    });
    expect(brief).not.toBeNull();
    expect(brief?.summary).toContain("Stable");
    expect(brief?.alerts).toHaveLength(1);
    expect(brief?.suggestions).toHaveLength(1);
  });

  it("returns null if Coordinator output is unparseable", async () => {
    const provider = makeProvider("not json");
    const registry = { getProviderForAgent: () => ({ provider, modelId: "m" }) } as any;
    const runner = createRiskMgrRunner({ registry });
    const brief = await runner.generateBrief({
      windowMs: 3600000,
      systemState: {
        portfolioState: { current_equity: 10000, day_start_equity: 10000, daily_halt_triggered: false },
        recentTrades: [],
        openPositionCount: 0,
      },
    });
    expect(brief).toBeNull();
  });
});
```

- [ ] **Step 3: Implementation `packages/llm/src/runners/risk-mgr-runner.ts`**

```typescript
import type { ProviderRegistry } from "../registry.js";
import { RISK_MANAGER_SYSTEM_PROMPT } from "./personas/risk-manager.js";

export interface SystemStateSnapshot {
  portfolioState: {
    current_equity: number;
    day_start_equity: number;
    daily_halt_triggered: boolean;
  };
  recentTrades: Array<{
    market_title: string;
    direction: string;
    pnl_net_usdc: number | null;
    exit_reason: string | null;
  }>;
  openPositionCount: number;
}

export interface CoordinatorBrief {
  summary: string;
  alerts: Array<{ severity: "info" | "warning" | "critical"; text: string }>;
  suggestions: string[];
}

export interface RiskMgrRunner {
  answerQuestion(input: { question: string; systemState: SystemStateSnapshot }): Promise<string>;
  generateBrief(input: { windowMs: number; systemState: SystemStateSnapshot }): Promise<CoordinatorBrief | null>;
}

function formatSystemState(state: SystemStateSnapshot): string {
  const lines: string[] = [];
  lines.push(`current_equity: $${state.portfolioState.current_equity.toFixed(2)}`);
  lines.push(`day_start_equity: $${state.portfolioState.day_start_equity.toFixed(2)}`);
  const dailyDdPct = ((state.portfolioState.current_equity - state.portfolioState.day_start_equity) / state.portfolioState.day_start_equity) * 100;
  lines.push(`daily_pnl_pct: ${dailyDdPct.toFixed(2)}%`);
  lines.push(`daily_halt_triggered: ${state.portfolioState.daily_halt_triggered}`);
  lines.push(`open_position_count: ${state.openPositionCount}`);
  if (state.recentTrades.length > 0) {
    lines.push(`recent_trades:`);
    for (const t of state.recentTrades.slice(0, 5)) {
      lines.push(
        `  - ${t.market_title} | ${t.direction} | pnl=${t.pnl_net_usdc?.toFixed(2) ?? "open"} | exit=${t.exit_reason ?? "none"}`
      );
    }
  }
  return lines.join("\n");
}

export function createRiskMgrRunner(opts: { registry: ProviderRegistry }): RiskMgrRunner {
  return {
    async answerQuestion({ question, systemState }) {
      const assigned = opts.registry.getProviderForAgent("risk_manager");
      if (!assigned) return "(Risk Manager not configured. Set a model in Settings.)";
      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: RISK_MANAGER_SYSTEM_PROMPT },
            {
              role: "user",
              content: `MODE: reactive\n\nSystem state:\n${formatSystemState(systemState)}\n\nQuestion: ${question}`,
            },
          ],
          temperature: 0.3,
          maxTokens: 500,
        });
        return resp.content;
      } catch (err) {
        return `(Error contacting Risk Manager: ${String(err).slice(0, 100)})`;
      }
    },

    async generateBrief({ windowMs, systemState }) {
      const assigned = opts.registry.getProviderForAgent("risk_manager");
      if (!assigned) return null;

      try {
        const resp = await assigned.provider.chat({
          model: assigned.modelId,
          messages: [
            { role: "system", content: RISK_MANAGER_SYSTEM_PROMPT },
            {
              role: "user",
              content: `MODE: proactive\nObservation window: ${Math.floor(windowMs / 60000)} minutes\n\nSystem state:\n${formatSystemState(systemState)}\n\nGenerate the Coordinator brief JSON.`,
            },
          ],
          temperature: 0.4,
          maxTokens: 600,
        });
        return parseBrief(resp.content);
      } catch {
        return null;
      }
    },
  };
}

function parseBrief(text: string): CoordinatorBrief | null {
  const fenceMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
  const jsonText = fenceMatch ? fenceMatch[1] : text;
  if (!jsonText) return null;
  try {
    const obj = JSON.parse(jsonText);
    if (typeof obj !== "object" || obj === null) return null;
    const o = obj as Record<string, unknown>;
    if (typeof o.summary !== "string") return null;
    const alerts = Array.isArray(o.alerts) ? (o.alerts as any[]) : [];
    const suggestions = Array.isArray(o.suggestions) ? (o.suggestions as any[]) : [];
    return {
      summary: o.summary,
      alerts: alerts.filter((a) => a && typeof a.severity === "string" && typeof a.text === "string"),
      suggestions: suggestions.filter((s) => typeof s === "string"),
    };
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Run + commit**

```bash
pnpm --filter @pmt/llm test:run tests/runners/risk-mgr-runner.test.ts
git add packages/llm/src/runners/personas/risk-manager.ts packages/llm/src/runners/risk-mgr-runner.ts packages/llm/tests/runners/risk-mgr-runner.test.ts
git commit -m "feat(llm): add risk-mgr runner with reactive + proactive Coordinator modes"
```

### Task M2.11: Public exports

**File:** `packages/llm/src/index.ts`

- [ ] **Step 1: Replace contents**

```typescript
// Public exports of @pmt/llm
export type {
  AgentId,
  ProviderId,
  AuthType,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ChatChunk,
  ProviderModelInfo,
  ProviderConnectionState,
  LlmProvider,
} from "./types.js";
export { ProviderError } from "./types.js";

export type { ProviderRegistry, AgentAssignment } from "./registry.js";
export { createProviderRegistry } from "./registry.js";

export { resolveProviderForModel } from "./routing.js";

export { createOpenAICompatProvider } from "./adapters/openai-compat.js";
export type { OpenAICompatConfig } from "./adapters/openai-compat.js";
export { createAnthropicProvider } from "./adapters/anthropic.js";
export type { AnthropicConfig } from "./adapters/anthropic.js";
export { createGeminiProvider } from "./adapters/gemini.js";
export type { GeminiConfig } from "./adapters/gemini.js";
export { createBedrockProvider } from "./adapters/bedrock.js";
export type { BedrockConfig } from "./adapters/bedrock.js";
export { createOllamaProvider } from "./adapters/ollama.js";
export type { OllamaConfig } from "./adapters/ollama.js";

export { createAnalyzerRunner } from "./runners/analyzer-runner.js";
export type { AnalyzerRunner, ParsedVerdict, TriggerEvent } from "./runners/analyzer-runner.js";
export { createReviewerRunner } from "./runners/reviewer-runner.js";
export type { ReviewerRunner, ReviewerInput, BucketStat } from "./runners/reviewer-runner.js";
export { createRiskMgrRunner } from "./runners/risk-mgr-runner.js";
export type { RiskMgrRunner, CoordinatorBrief, SystemStateSnapshot } from "./runners/risk-mgr-runner.js";

export const PACKAGE_NAME = "@pmt/llm";
```

- [ ] **Step 2: Build full package**

```bash
pnpm --filter @pmt/llm build
pnpm --filter @pmt/llm test:run
```

Expected: build succeeds, all tests pass (~25 in @pmt/llm).

- [ ] **Step 3: Commit**

```bash
git add packages/llm/src/index.ts
git commit -m "feat(llm): wire all public exports through index"
```

---

## M2 Verification Gate

- [ ] **Run full workspace**

```bash
cd D:/work/polymarket-trader
pnpm test:run
pnpm typecheck
pnpm build
```

Expected:
- @pmt/engine: 166 tests
- @pmt/llm: ~25 tests
- @pmt/main: 5 tests
- @pmt/renderer: 1 test
- **Total ~197 tests passing**
- All packages build cleanly
- No type errors

If any failure, fix before M3.

---

## M3 — Electron Main Process (~12 tasks)

Goal: Electron app boots with a tray icon, opens an empty window, and the trading engine runs in the background. No real LLM calls yet (Analyzer/Reviewer/Coordinator stubs use the registry but no providers are connected). UI is empty placeholder.

### Task M3.1: Engine boot module

**Files:**
- Create: `packages/main/src/lifecycle.ts`
- Create: `packages/main/tests/lifecycle.test.ts`

- [ ] **Step 1: Failing test**

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { bootEngine, shutdownEngine } from "../src/lifecycle.js";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { rmSync, mkdirSync } from "node:fs";

vi.mock("electron", () => ({
  app: {
    getPath: (kind: string) => {
      if (kind === "userData") return join(tmpdir(), "pmt-test-" + Date.now());
      throw new Error("unexpected getPath: " + kind);
    },
  },
  safeStorage: {
    isEncryptionAvailable: () => true,
    encryptString: (s: string) => Buffer.from("enc:" + s),
    decryptString: (b: Buffer) => b.toString().replace(/^enc:/, ""),
  },
}));

describe("engine lifecycle", () => {
  let testDir: string;

  beforeEach(() => {
    testDir = join(tmpdir(), "pmt-engine-test-" + Date.now());
    mkdirSync(testDir, { recursive: true });
    process.env.POLYMARKET_TRADER_HOME = testDir;
  });

  afterEach(async () => {
    await shutdownEngine();
    rmSync(testDir, { recursive: true, force: true });
    delete process.env.POLYMARKET_TRADER_HOME;
  });

  it("boots engine and returns context with db, registry, collector, executor", async () => {
    const ctx = await bootEngine();
    expect(ctx.db).toBeDefined();
    expect(ctx.registry).toBeDefined();
    expect(ctx.collector).toBeDefined();
    expect(ctx.executor).toBeDefined();
    expect(ctx.bus).toBeDefined();
  });

  it("creates data.db at expected path", async () => {
    const ctx = await bootEngine();
    const dbPath = ctx.dbPath;
    expect(dbPath).toContain(testDir);
    expect(dbPath).toContain("data.db");
  });

  it("shutdownEngine closes the database", async () => {
    const ctx = await bootEngine();
    await shutdownEngine();
    // After shutdown, db should be closed; calling .prepare() should throw
    expect(() => ctx.db.prepare("SELECT 1")).toThrow();
  });

  it("can boot, shutdown, and re-boot without errors", async () => {
    const ctx1 = await bootEngine();
    expect(ctx1.db.open).toBe(true);
    await shutdownEngine();
    const ctx2 = await bootEngine();
    expect(ctx2.db.open).toBe(true);
  });
});
```

- [ ] **Step 2: Run, verify fails**

```bash
pnpm --filter @pmt/main test:run tests/lifecycle.test.ts
```

- [ ] **Step 3: Implement `packages/main/src/lifecycle.ts`**

```typescript
import { app } from "electron";
import { join } from "node:path";
import { homedir } from "node:os";
import type Database from "better-sqlite3";
import { openDatabase } from "@pmt/engine/db";
import {
  createEventBus,
  createCollector,
  createExecutor,
  createSignalLogRepo,
  createPortfolioStateRepo,
  loadConfig,
  createPolymarketWsClient,
  type EventBus,
  type Collector,
  type Executor,
  type TraderConfig,
} from "@pmt/engine";
import { createProviderRegistry, type ProviderRegistry } from "@pmt/llm";

export interface EngineContext {
  db: Database.Database;
  dbPath: string;
  config: TraderConfig;
  bus: EventBus;
  collector: Collector;
  executor: Executor;
  registry: ProviderRegistry;
}

let activeContext: EngineContext | null = null;

function resolveDataDir(): string {
  if (process.env.POLYMARKET_TRADER_HOME?.trim()) {
    return process.env.POLYMARKET_TRADER_HOME;
  }
  // In Electron context, prefer userData; fall back to ~/.polymarket-trader
  try {
    return app.getPath("userData");
  } catch {
    return join(homedir(), ".polymarket-trader");
  }
}

export async function bootEngine(): Promise<EngineContext> {
  if (activeContext) return activeContext;

  const dataDir = resolveDataDir();
  const dbPath = join(dataDir, "data.db");
  const db = openDatabase(dbPath);

  const config = loadConfig(undefined);
  const signalRepo = createSignalLogRepo(db);
  const portfolioRepo = createPortfolioStateRepo(db);
  const bus = createEventBus();
  const registry = createProviderRegistry();

  const noopLogger = {
    info: () => {},
    warn: () => {},
    error: () => {},
  };

  const collector = createCollector({
    config,
    bus,
    wsClientFactory: (onTrade) =>
      createPolymarketWsClient({
        url: config.polymarketWsUrl,
        onTrade,
        onError: () => {},
      }),
    marketMetadataProvider: async (marketId) => ({
      marketId,
      marketTitle: marketId, // M3 stub — M5 wires real Gamma API
      resolvesAt: Date.now() + 86_400_000,
      liquidity: 10_000,
    }),
    logger: noopLogger,
  });

  const executor = createExecutor({
    config,
    bus,
    signalRepo,
    portfolioRepo,
    logger: noopLogger,
  });

  activeContext = {
    db,
    dbPath,
    config,
    bus,
    collector,
    executor,
    registry,
  };
  return activeContext;
}

export async function shutdownEngine(): Promise<void> {
  if (!activeContext) return;
  try {
    activeContext.collector.stop();
  } catch {}
  try {
    activeContext.db.close();
  } catch {}
  activeContext = null;
}

export function getEngineContext(): EngineContext | null {
  return activeContext;
}
```

- [ ] **Step 4: Run, verify pass**

```bash
pnpm --filter @pmt/main test:run tests/lifecycle.test.ts
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add packages/main/src/lifecycle.ts packages/main/tests/lifecycle.test.ts
git commit -m "feat(main): add engine lifecycle (boot/shutdown)"
```

### Task M3.2: Tray module

**Files:**
- Create: `packages/main/src/tray.ts`
- Create: `packages/main/tests/tray.test.ts` (basic constructor test only — full UI test in M5)

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { createTray } from "../src/tray.js";

vi.mock("electron", () => ({
  Tray: vi.fn().mockImplementation(() => ({
    setToolTip: vi.fn(),
    setContextMenu: vi.fn(),
    on: vi.fn(),
    destroy: vi.fn(),
  })),
  Menu: {
    buildFromTemplate: vi.fn().mockReturnValue({}),
  },
  nativeImage: {
    createFromPath: vi.fn().mockReturnValue({}),
    createEmpty: vi.fn().mockReturnValue({}),
  },
}));

describe("tray", () => {
  it("creates a tray with a default menu", () => {
    const onShowWindow = vi.fn();
    const onQuit = vi.fn();
    const tray = createTray({ iconPath: undefined, onShowWindow, onQuit });
    expect(tray).toBeDefined();
    expect(tray.destroy).toBeDefined();
  });
});
```

- [ ] **Step 2: Implement `packages/main/src/tray.ts`**

```typescript
import { Tray, Menu, nativeImage, type MenuItemConstructorOptions } from "electron";

export interface TrayDeps {
  iconPath?: string | undefined;
  onShowWindow: () => void;
  onQuit: () => void;
}

export interface TrayHandle {
  destroy(): void;
  updateStatus(status: TrayStatus): void;
}

export type TrayStatus =
  | { kind: "running"; positionCount: number; equity: number }
  | { kind: "halted"; reason: string }
  | { kind: "error"; message: string };

export function createTray(deps: TrayDeps): TrayHandle {
  const icon = deps.iconPath
    ? nativeImage.createFromPath(deps.iconPath)
    : nativeImage.createEmpty();
  const tray = new Tray(icon);
  tray.setToolTip("Polymarket Trader");

  let currentStatus: TrayStatus = { kind: "running", positionCount: 0, equity: 0 };

  function buildMenu(): Menu {
    const statusLabel = formatStatusLabel(currentStatus);
    const items: MenuItemConstructorOptions[] = [
      { label: statusLabel, enabled: false },
      { type: "separator" },
      { label: "Show Window", click: deps.onShowWindow },
      { type: "separator" },
      { label: "Quit", click: deps.onQuit },
    ];
    return Menu.buildFromTemplate(items);
  }

  tray.setContextMenu(buildMenu());
  tray.on("double-click", deps.onShowWindow);

  return {
    destroy() {
      tray.destroy();
    },
    updateStatus(status) {
      currentStatus = status;
      tray.setContextMenu(buildMenu());
      tray.setToolTip(`Polymarket Trader — ${formatStatusLabel(status)}`);
    },
  };
}

function formatStatusLabel(status: TrayStatus): string {
  switch (status.kind) {
    case "running":
      return `Running · ${status.positionCount} positions · $${status.equity.toFixed(0)}`;
    case "halted":
      return `Halted: ${status.reason}`;
    case "error":
      return `Error: ${status.message.slice(0, 40)}`;
  }
}
```

- [ ] **Step 3: Run, verify pass + commit**

```bash
pnpm --filter @pmt/main test:run tests/tray.test.ts
git add packages/main/src/tray.ts packages/main/tests/tray.test.ts
git commit -m "feat(main): add system tray with status display"
```

### Task M3.3: Window management

**Files:**
- Create: `packages/main/src/window.ts`

- [ ] **Step 1: Implement `packages/main/src/window.ts`** (no test — UI behavior, tested via E2E later)

```typescript
import { BrowserWindow, app } from "electron";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

export interface WindowDeps {
  preloadPath: string;
  rendererUrl: string;
  /** dev mode: load from Vite dev server. prod mode: load from file:// */
  isDev: boolean;
}

export interface WindowHandle {
  show(): void;
  hide(): void;
  close(): void;
  isVisible(): boolean;
  webContents(): Electron.WebContents;
}

export function createMainWindow(deps: WindowDeps): WindowHandle {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false, // start hidden, tray controls visibility
    title: "Polymarket Trader",
    webPreferences: {
      preload: deps.preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (deps.isDev) {
    window.loadURL(deps.rendererUrl);
    window.webContents.openDevTools();
  } else {
    window.loadFile(deps.rendererUrl);
  }

  // Don't actually quit on close — hide to tray instead
  window.on("close", (e) => {
    if (!app.isQuittingExplicit) {
      e.preventDefault();
      window.hide();
    }
  });

  return {
    show() {
      window.show();
      window.focus();
    },
    hide() {
      window.hide();
    },
    close() {
      app.isQuittingExplicit = true;
      window.close();
    },
    isVisible() {
      return window.isVisible();
    },
    webContents() {
      return window.webContents;
    },
  };
}

// Augment Electron App type with our explicit quit flag
declare module "electron" {
  interface App {
    isQuittingExplicit?: boolean;
  }
}
```

- [ ] **Step 2: Build to verify type-correctness**

```bash
pnpm --filter @pmt/main build
```

- [ ] **Step 3: Commit**

```bash
git add packages/main/src/window.ts
git commit -m "feat(main): add main window management with hide-to-tray behavior"
```

### Task M3.4: Electron app entry (`packages/main/src/index.ts`)

**Files:**
- Modify: `packages/main/src/index.ts` (replace stub with real entry)

- [ ] **Step 1: Replace contents**

```typescript
/**
 * @pmt/main — Electron main process entry.
 *
 * Lifecycle:
 *   1. app.whenReady → boot engine, create window + tray
 *   2. window-all-closed → keep alive (tray runs in background)
 *   3. before-quit → shutdown engine
 */
import { app } from "electron";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { bootEngine, shutdownEngine, getEngineContext } from "./lifecycle.js";
import { createTray, type TrayHandle } from "./tray.js";
import { createMainWindow, type WindowHandle } from "./window.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const preloadPath = join(__dirname, "preload.js");
const isDev = process.env.NODE_ENV === "development";
const rendererUrl = isDev
  ? (process.env.VITE_DEV_SERVER_URL ?? "http://localhost:5173")
  : join(__dirname, "..", "..", "renderer", "dist", "index.html");

let mainWindow: WindowHandle | null = null;
let tray: TrayHandle | null = null;

async function onReady(): Promise<void> {
  await bootEngine();

  mainWindow = createMainWindow({ preloadPath, rendererUrl, isDev });

  tray = createTray({
    iconPath: undefined, // M7 will add a real icon
    onShowWindow: () => mainWindow?.show(),
    onQuit: () => {
      app.isQuittingExplicit = true;
      app.quit();
    },
  });

  mainWindow.show();
}

app.whenReady().then(onReady).catch((err) => {
  console.error("[pmt-main] failed to start:", err);
  app.quit();
});

app.on("window-all-closed", () => {
  // Don't quit — tray keeps the app alive
  // (On macOS this is also the default behavior)
});

app.on("before-quit", async () => {
  await shutdownEngine();
});

app.on("activate", () => {
  // macOS: re-show window when dock icon is clicked
  mainWindow?.show();
});

export const PACKAGE_NAME = "@pmt/main";
```

- [ ] **Step 2: Build, verify**

```bash
pnpm --filter @pmt/main build
```

Expected: build succeeds. The actual app cannot be tested headlessly — manual run happens after M5.

- [ ] **Step 3: Commit**

```bash
git add packages/main/src/index.ts
git commit -m "feat(main): wire Electron app entry with engine boot + tray + window"
```

### Task M3.5: Reviewer scheduler (daily)

The engine has `runReviewer()` but no scheduler. The main process is responsible for triggering it on cron-like schedule.

**Files:**
- Create: `packages/main/src/reviewer-scheduler.ts`
- Create: `packages/main/tests/reviewer-scheduler.test.ts`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createReviewerScheduler } from "../src/reviewer-scheduler.js";

describe("reviewerScheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("invokes reviewer on first start when never run before", async () => {
    const runReviewer = vi.fn().mockResolvedValue({ bucketCount: 0, killSwitches: 0, reportPath: "" });
    const scheduler = createReviewerScheduler({
      runReviewer,
      lastRunAt: () => null,
      onRun: vi.fn(),
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    expect(runReviewer).toHaveBeenCalledTimes(1);
  });

  it("waits 24 hours between runs after a successful run", async () => {
    const runReviewer = vi.fn().mockResolvedValue({ bucketCount: 0, killSwitches: 0, reportPath: "" });
    let lastRun = Date.now();
    const scheduler = createReviewerScheduler({
      runReviewer,
      lastRunAt: () => lastRun,
      onRun: () => {
        lastRun = Date.now();
      },
    });
    scheduler.start();
    await vi.advanceTimersByTimeAsync(60 * 60 * 1000); // 1 hour
    expect(runReviewer).toHaveBeenCalledTimes(0); // not yet
    await vi.advanceTimersByTimeAsync(23 * 60 * 60 * 1000); // 23 more hours = 24h total
    expect(runReviewer).toHaveBeenCalledTimes(1);
  });

  it("stop() clears the timer", async () => {
    const runReviewer = vi.fn().mockResolvedValue({ bucketCount: 0, killSwitches: 0, reportPath: "" });
    const scheduler = createReviewerScheduler({
      runReviewer,
      lastRunAt: () => Date.now(),
      onRun: vi.fn(),
    });
    scheduler.start();
    scheduler.stop();
    await vi.advanceTimersByTimeAsync(48 * 60 * 60 * 1000);
    expect(runReviewer).toHaveBeenCalledTimes(0);
  });
});
```

- [ ] **Step 2: Implement `packages/main/src/reviewer-scheduler.ts`**

```typescript
const ONE_DAY_MS = 24 * 60 * 60 * 1000;
const CHECK_INTERVAL_MS = 60 * 60 * 1000; // re-evaluate every hour

export interface ReviewerSchedulerDeps {
  runReviewer: () => Promise<{ bucketCount: number; killSwitches: number; reportPath: string }>;
  lastRunAt: () => number | null;
  onRun: () => void;
}

export interface ReviewerScheduler {
  start(): void;
  stop(): void;
  triggerNow(): Promise<void>;
}

export function createReviewerScheduler(deps: ReviewerSchedulerDeps): ReviewerScheduler {
  let timer: NodeJS.Timeout | null = null;

  async function maybeRun(): Promise<void> {
    const last = deps.lastRunAt();
    const now = Date.now();
    if (last === null || now - last >= ONE_DAY_MS) {
      try {
        await deps.runReviewer();
        deps.onRun();
      } catch (err) {
        console.error("[reviewer-scheduler] run failed:", err);
      }
    }
  }

  return {
    start() {
      // Initial check immediately, then every hour
      maybeRun();
      timer = setInterval(maybeRun, CHECK_INTERVAL_MS);
    },
    stop() {
      if (timer) clearInterval(timer);
      timer = null;
    },
    async triggerNow() {
      await deps.runReviewer();
      deps.onRun();
    },
  };
}
```

- [ ] **Step 3: Run + commit**

```bash
pnpm --filter @pmt/main test:run tests/reviewer-scheduler.test.ts
git add packages/main/src/reviewer-scheduler.ts packages/main/tests/reviewer-scheduler.test.ts
git commit -m "feat(main): add daily Reviewer scheduler"
```

### Task M3.6: Coordinator scheduler (hourly)

**Files:**
- Create: `packages/main/src/coordinator.ts`
- Create: `packages/main/tests/coordinator.test.ts`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createCoordinatorScheduler } from "../src/coordinator.js";

describe("coordinatorScheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("runs at the configured interval", async () => {
    const generateBrief = vi.fn().mockResolvedValue({
      summary: "test",
      alerts: [],
      suggestions: [],
    });
    const onBrief = vi.fn();
    const scheduler = createCoordinatorScheduler({
      intervalMs: 60 * 60 * 1000,
      generateBrief,
      onBrief,
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync(); // initial run
    expect(generateBrief).toHaveBeenCalledTimes(1);
    expect(onBrief).toHaveBeenCalledWith({
      summary: "test",
      alerts: [],
      suggestions: [],
    });
    await vi.advanceTimersByTimeAsync(60 * 60 * 1000);
    expect(generateBrief).toHaveBeenCalledTimes(2);
  });

  it("does not call onBrief if generateBrief returns null", async () => {
    const generateBrief = vi.fn().mockResolvedValue(null);
    const onBrief = vi.fn();
    const scheduler = createCoordinatorScheduler({
      intervalMs: 60 * 60 * 1000,
      generateBrief,
      onBrief,
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    expect(generateBrief).toHaveBeenCalledTimes(1);
    expect(onBrief).not.toHaveBeenCalled();
  });

  it("stop() halts further runs", async () => {
    const generateBrief = vi.fn().mockResolvedValue({ summary: "x", alerts: [], suggestions: [] });
    const scheduler = createCoordinatorScheduler({
      intervalMs: 60 * 60 * 1000,
      generateBrief,
      onBrief: vi.fn(),
    });
    scheduler.start();
    await vi.runOnlyPendingTimersAsync();
    scheduler.stop();
    await vi.advanceTimersByTimeAsync(2 * 60 * 60 * 1000);
    expect(generateBrief).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Implement `packages/main/src/coordinator.ts`**

```typescript
import type { CoordinatorBrief } from "@pmt/llm";

export interface CoordinatorSchedulerDeps {
  intervalMs: number;
  generateBrief: () => Promise<CoordinatorBrief | null>;
  onBrief: (brief: CoordinatorBrief) => void;
}

export interface CoordinatorScheduler {
  start(): void;
  stop(): void;
  triggerNow(): Promise<CoordinatorBrief | null>;
}

export function createCoordinatorScheduler(deps: CoordinatorSchedulerDeps): CoordinatorScheduler {
  let timer: NodeJS.Timeout | null = null;

  async function runOnce(): Promise<CoordinatorBrief | null> {
    try {
      const brief = await deps.generateBrief();
      if (brief) deps.onBrief(brief);
      return brief;
    } catch (err) {
      console.error("[coordinator] run failed:", err);
      return null;
    }
  }

  return {
    start() {
      runOnce(); // initial
      timer = setInterval(runOnce, deps.intervalMs);
    },
    stop() {
      if (timer) clearInterval(timer);
      timer = null;
    },
    async triggerNow() {
      return runOnce();
    },
  };
}
```

- [ ] **Step 3: Run + commit**

```bash
pnpm --filter @pmt/main test:run tests/coordinator.test.ts
git add packages/main/src/coordinator.ts packages/main/tests/coordinator.test.ts
git commit -m "feat(main): add hourly Coordinator scheduler"
```

### Task M3.7: Auto-apply for filter proposals

**Files:**
- Create: `packages/main/src/auto-apply.ts`
- Create: `packages/main/tests/auto-apply.test.ts`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect, vi } from "vitest";
import { evaluateAutoApply } from "../src/auto-apply.js";

describe("auto-apply", () => {
  it("approves a high-confidence proposal", () => {
    const decision = evaluateAutoApply({
      sample_count: 35,
      expected_delta_winrate: 0.06,
      field: "min_net_flow_1m",
      proposed_value: "3500",
    });
    expect(decision.shouldApply).toBe(true);
  });

  it("rejects when sample_count too small", () => {
    const decision = evaluateAutoApply({
      sample_count: 20,
      expected_delta_winrate: 0.10,
      field: "min_net_flow_1m",
      proposed_value: "3500",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("sample");
  });

  it("rejects when expected delta winrate too small", () => {
    const decision = evaluateAutoApply({
      sample_count: 50,
      expected_delta_winrate: 0.03,
      field: "min_net_flow_1m",
      proposed_value: "3500",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("delta");
  });

  it("rejects locked field even with high confidence", () => {
    const decision = evaluateAutoApply({
      sample_count: 100,
      expected_delta_winrate: 0.20,
      field: "static_dead_zone_min",
      proposed_value: "0.55",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("locked");
  });

  it("rejects fields that affect max single trade loss", () => {
    const decision = evaluateAutoApply({
      sample_count: 100,
      expected_delta_winrate: 0.10,
      field: "max_single_trade_loss_usdc",
      proposed_value: "100",
    });
    expect(decision.shouldApply).toBe(false);
    expect(decision.reason).toContain("loss");
  });
});
```

- [ ] **Step 2: Implement `packages/main/src/auto-apply.ts`**

```typescript
const MIN_SAMPLE_COUNT = 30;
const MIN_DELTA_WINRATE = 0.05;

const LOCKED_FIELDS = new Set([
  "static_dead_zone_min",
  "static_dead_zone_max",
  "kelly_multiplier",
  "max_total_position_usdc",
]);

const LOSS_AFFECTING_FIELDS = new Set([
  "max_single_trade_loss_usdc",
  "stop_loss_pct_normal",
  "stop_loss_pct_late_stage",
  "max_position_usdc",
]);

export interface AutoApplyInput {
  sample_count: number;
  expected_delta_winrate: number | null;
  field: string;
  proposed_value: string;
}

export interface AutoApplyDecision {
  shouldApply: boolean;
  reason: string;
}

/**
 * Decides whether a Reviewer-generated filter_proposal can be auto-applied
 * without human approval. The criteria are intentionally strict:
 *
 *   1. Sample size >= MIN_SAMPLE_COUNT (30 trades) — small samples are noise
 *   2. Expected win rate improvement >= MIN_DELTA_WINRATE (5%) — small wins
 *      aren't worth the risk of an LLM hallucination
 *   3. Field is not in LOCKED_FIELDS — these are spec hard limits
 *   4. Field doesn't affect max single trade loss — those changes need human eyes
 */
export function evaluateAutoApply(input: AutoApplyInput): AutoApplyDecision {
  if (LOCKED_FIELDS.has(input.field)) {
    return {
      shouldApply: false,
      reason: `field ${input.field} is locked (spec hard constraint)`,
    };
  }
  if (LOSS_AFFECTING_FIELDS.has(input.field)) {
    return {
      shouldApply: false,
      reason: `field ${input.field} affects max single trade loss — human review required`,
    };
  }
  if (input.sample_count < MIN_SAMPLE_COUNT) {
    return {
      shouldApply: false,
      reason: `sample size ${input.sample_count} < min ${MIN_SAMPLE_COUNT}`,
    };
  }
  if (input.expected_delta_winrate === null || input.expected_delta_winrate < MIN_DELTA_WINRATE) {
    return {
      shouldApply: false,
      reason: `expected delta winrate ${input.expected_delta_winrate ?? "null"} < min ${MIN_DELTA_WINRATE}`,
    };
  }
  return {
    shouldApply: true,
    reason: `${input.sample_count} samples + ${(input.expected_delta_winrate * 100).toFixed(1)}% expected delta — auto-applied`,
  };
}
```

- [ ] **Step 3: Run + commit**

```bash
pnpm --filter @pmt/main test:run tests/auto-apply.test.ts
git add packages/main/src/auto-apply.ts packages/main/tests/auto-apply.test.ts
git commit -m "feat(main): add auto-apply decision logic for filter proposals"
```

### Task M3.8: Notifications module (OS desktop notifications)

**Files:**
- Create: `packages/main/src/notifications.ts`

- [ ] **Step 1: Implement (no test — wraps Electron Notification, manual smoke later)**

```typescript
import { Notification } from "electron";

export interface DesktopNotification {
  title: string;
  body: string;
  silent?: boolean;
}

export function showNotification(input: DesktopNotification): void {
  if (!Notification.isSupported()) return;
  new Notification({
    title: input.title,
    body: input.body,
    silent: input.silent ?? false,
  }).show();
}
```

- [ ] **Step 2: Build + commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/notifications.ts
git commit -m "feat(main): add OS desktop notification helper"
```

### Task M3.9: Wire all schedulers + IPC stub into app entry

This task brings together engine boot, tray, window, schedulers — but stops short of IPC handlers (those come in M5). The result is a runnable Electron app whose engine processes WS data, tray shows status, and Reviewer/Coordinator schedulers tick — but no UI yet (renderer is the placeholder from M1.5).

**Files:**
- Modify: `packages/main/src/index.ts`

- [ ] **Step 1: Replace contents**

```typescript
/**
 * @pmt/main — Electron main process entry.
 *
 * M3 wiring: engine + tray + window + schedulers. No IPC, no LLM.
 * M5 will add IPC handlers and connect the UI.
 */
import { app } from "electron";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { bootEngine, shutdownEngine, getEngineContext } from "./lifecycle.js";
import { createTray, type TrayHandle } from "./tray.js";
import { createMainWindow, type WindowHandle } from "./window.js";
import { createReviewerScheduler, type ReviewerScheduler } from "./reviewer-scheduler.js";
import { createCoordinatorScheduler, type CoordinatorScheduler } from "./coordinator.js";
import { runReviewer } from "@pmt/engine/reviewer";
import { createStrategyPerformanceRepo, createSignalLogRepo } from "@pmt/engine";
import { createRiskMgrRunner } from "@pmt/llm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const preloadPath = join(__dirname, "preload.js");
const isDev = process.env.NODE_ENV === "development";
const rendererUrl = isDev
  ? (process.env.VITE_DEV_SERVER_URL ?? "http://localhost:5173")
  : join(__dirname, "..", "..", "renderer", "dist", "index.html");

let mainWindow: WindowHandle | null = null;
let tray: TrayHandle | null = null;
let reviewerScheduler: ReviewerScheduler | null = null;
let coordinatorScheduler: CoordinatorScheduler | null = null;

async function onReady(): Promise<void> {
  const ctx = await bootEngine();

  mainWindow = createMainWindow({ preloadPath, rendererUrl, isDev });

  tray = createTray({
    iconPath: undefined,
    onShowWindow: () => mainWindow?.show(),
    onQuit: () => {
      app.isQuittingExplicit = true;
      app.quit();
    },
  });

  // Reviewer scheduler — daily
  reviewerScheduler = createReviewerScheduler({
    runReviewer: async () =>
      runReviewer({
        db: ctx.db,
        config: ctx.config,
        signalRepo: createSignalLogRepo(ctx.db),
        strategyPerfRepo: createStrategyPerformanceRepo(ctx.db),
        logger: { info: () => {}, warn: () => {}, error: () => {} },
      }),
    lastRunAt: () => {
      // Read from app_state table
      const row = ctx.db
        .prepare("SELECT value FROM app_state WHERE key = ?")
        .get("reviewer_last_run") as { value: string } | undefined;
      return row ? Number(row.value) : null;
    },
    onRun: () => {
      ctx.db
        .prepare(
          "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at"
        )
        .run("reviewer_last_run", String(Date.now()), Date.now());
    },
  });
  reviewerScheduler.start();

  // Coordinator scheduler — hourly
  const riskMgrRunner = createRiskMgrRunner({ registry: ctx.registry });
  coordinatorScheduler = createCoordinatorScheduler({
    intervalMs: 60 * 60 * 1000,
    generateBrief: async () => {
      const portfolioRow = ctx.db
        .prepare("SELECT key, value FROM portfolio_state")
        .all() as Array<{ key: string; value: string }>;
      const portfolioState = Object.fromEntries(
        portfolioRow.map((r) => [r.key, JSON.parse(r.value)])
      );
      const recentTradeRows = ctx.db
        .prepare(
          "SELECT market_title, direction, pnl_net_usdc, exit_reason FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT 5"
        )
        .all() as Array<{
        market_title: string;
        direction: string;
        pnl_net_usdc: number | null;
        exit_reason: string | null;
      }>;
      const openCount = ctx.db
        .prepare("SELECT COUNT(*) as n FROM signal_log WHERE exit_at IS NULL")
        .get() as { n: number };

      return riskMgrRunner.generateBrief({
        windowMs: 60 * 60 * 1000,
        systemState: {
          portfolioState: {
            current_equity: portfolioState.current_equity ?? 10000,
            day_start_equity: portfolioState.day_start_equity ?? 10000,
            daily_halt_triggered: portfolioState.daily_halt_triggered ?? false,
          },
          recentTrades: recentTradeRows,
          openPositionCount: openCount.n,
        },
      });
    },
    onBrief: (brief) => {
      ctx.db
        .prepare(
          "INSERT INTO coordinator_log (generated_at, summary, alerts, suggestions, context_snapshot, model_used) VALUES (?, ?, ?, ?, ?, ?)"
        )
        .run(
          Date.now(),
          brief.summary,
          JSON.stringify(brief.alerts),
          JSON.stringify(brief.suggestions),
          "{}",
          ""
        );
    },
  });
  coordinatorScheduler.start();

  // Start collector (engine WS subscription)
  await ctx.collector.start();

  mainWindow.show();
}

app.whenReady().then(onReady).catch((err) => {
  console.error("[pmt-main] failed to start:", err);
  app.quit();
});

app.on("window-all-closed", () => {
  // tray keeps app alive
});

app.on("before-quit", async () => {
  reviewerScheduler?.stop();
  coordinatorScheduler?.stop();
  await shutdownEngine();
});

app.on("activate", () => {
  mainWindow?.show();
});

export const PACKAGE_NAME = "@pmt/main";
```

- [ ] **Step 2: Build, verify**

```bash
pnpm --filter @pmt/main build
```

- [ ] **Step 3: Commit**

```bash
git add packages/main/src/index.ts
git commit -m "feat(main): wire schedulers and engine boot in app entry"
```

### Task M3.10: Empty preload.ts (placeholder for M5)

**Files:**
- Create: `packages/main/src/preload.ts`

- [ ] **Step 1: Implement**

```typescript
/**
 * Electron preload script.
 *
 * M3: empty placeholder. M5 will use contextBridge to expose typed IPC API.
 */
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("pmt", {
  __placeholder: true,
});
```

- [ ] **Step 2: Add preload to tsdown entry points**

Edit `packages/main/tsdown.config.ts`:

```typescript
import { defineConfig } from "tsdown";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    preload: "src/preload.ts",
  },
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: false,
  external: ["@pmt/engine", "@pmt/llm", "electron", "better-sqlite3", "ws"],
  outExtensions: () => ({ dts: ".d.ts" }),
});
```

- [ ] **Step 3: Build, commit**

```bash
pnpm --filter @pmt/main build
ls packages/main/dist/   # should show index.js, preload.js
git add packages/main/src/preload.ts packages/main/tsdown.config.ts
git commit -m "feat(main): add preload.ts placeholder for M5 IPC"
```

### Task M3.11: Manual smoke test of Electron app

This task is human-only — there's no automated way to verify Electron starts, the tray appears, and the (empty) window opens. Document the steps and expected output so the implementer / user can verify M3 success.

**Files:**
- Create: `packages/main/docs/m3-smoke-test.md`

- [ ] **Step 1: Write the doc**

```markdown
# M3 Smoke Test — Electron app starts

## Prerequisites
- M1 + M2 + M3 tasks all complete
- Engine tests pass: `pnpm test:run`

## Steps

### 1. Build all packages
\`\`\`bash
cd D:/work/polymarket-trader
pnpm build
\`\`\`

Expected: 4 dist directories, no errors.

### 2. Start Electron from main package
\`\`\`bash
cd packages/main
npx electron dist/index.js
\`\`\`

(In dev mode you would set `NODE_ENV=development` and have the renderer Vite server running, but for M3 smoke test we just want to see the empty placeholder window.)

### 3. Verify
- [ ] Tray icon appears in system tray
- [ ] Empty Electron window appears with title "Polymarket Trader"
- [ ] Closing the window hides it (does not quit) — tray icon stays
- [ ] Right-click tray → "Show Window" reopens it
- [ ] Right-click tray → "Quit" terminates the app

### 4. Verify engine is running
While the app is open, check:
- [ ] `~/.polymarket-trader/data.db` file was created
- [ ] No errors in the terminal log

### 5. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Cannot find module 'better-sqlite3'` | Native binding not rebuilt for Electron | Run `npx electron-rebuild -f -w better-sqlite3` (or whatever I3 chose) |
| Window stays blank forever | preload path wrong | Check that `dist/preload.js` exists |
| Tray icon doesn't appear (Linux) | Some distros don't show empty icons | OK for M3 — real icon comes in M7 |
| `app is not defined` import error | ESM/CJS interop issue | Check package.json type: "module" |
```

- [ ] **Step 2: Commit**

```bash
git add packages/main/docs/m3-smoke-test.md
git commit -m "docs(main): add M3 smoke test instructions"
```

### Task M3.12: Manually run the smoke test (one-time)

This task is the human verification gate. The implementer follows `m3-smoke-test.md` and reports back.

- [ ] **Step 1: Run electron**

```bash
cd D:/work/polymarket-trader
pnpm build
cd packages/main
npx electron dist/index.js
```

- [ ] **Step 2: Verify all checklist items in m3-smoke-test.md pass**

If any fail, debug and fix. Common fixes:
- Native rebuild for better-sqlite3 (per I3 findings)
- Path issues with preload (verify dist file structure)

- [ ] **Step 3: No commit needed unless code changes**

If you had to fix anything to make smoke test pass, commit those fixes:

```bash
git add -A
git commit -m "fix(main): smoke test fixes (describe what)"
```

---

## M3 Verification Gate

- [ ] All 12 M3 tasks complete
- [ ] `pnpm test:run` shows 197+ tests passing
- [ ] `pnpm build` succeeds for all packages
- [ ] `pnpm typecheck` clean
- [ ] Manual smoke test passes (m3-smoke-test.md checklist all green)
- [ ] Tray + empty window confirmed working on at least one OS

---

## M4 — React UI with Mocked Data (~20 tasks)

Goal: All 4 pages (Dashboard / Settings / Reports / Chat) render correctly with mocked data, in Kraken DESIGN.md style. UI looks like the brainstorm mockups. No real IPC yet — Zustand stores have hardcoded mock state.

### Task M4.1: Copy Kraken DESIGN.md and create theme tokens

**Files:**
- Create: `packages/renderer/DESIGN.md` (copy from awesome-design-md)
- Create: `packages/renderer/src/theme.ts`
- Create: `packages/renderer/src/styles/global.css`

- [ ] **Step 1: Copy the DESIGN.md**

Per spec §1.1.5 convention, Kraken is the chosen DESIGN.md for v1 UI styling.

```bash
cp C:/tmp/awesome-design-md/design-md/kraken/DESIGN.md packages/renderer/DESIGN.md
```

If `C:/tmp/awesome-design-md/` doesn't exist, clone it first:
```bash
git clone --depth 1 https://github.com/VoltAgent/awesome-design-md.git C:/tmp/awesome-design-md
```

- [ ] **Step 2: `packages/renderer/src/theme.ts`**

```typescript
export const theme = {
  colors: {
    // Brand
    purple: "#7132f5",
    purpleDark: "#5741d8",
    purpleDeep: "#5b1ecf",
    purpleSubtle: "rgba(133,91,251,0.16)",
    purpleBg: "rgba(133,91,251,0.04)",
    // Neutral
    nearBlack: "#101114",
    coolGray: "#686b82",
    silverBlue: "#9497a9",
    white: "#ffffff",
    fafafa: "#fafafa",
    borderGray: "#dedee5",
    rowDivider: "#f0f0f5",
    // Semantic
    green: "#149e61",
    greenDark: "#026b3f",
    greenSubtle: "rgba(20,158,97,0.16)",
    greenBg: "rgba(20,158,97,0.04)",
    red: "#d63b3b",
    redSubtle: "rgba(214,59,59,0.16)",
  },
  spacing: {
    xs: "4px",
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "20px",
    xxl: "24px",
    xxxl: "32px",
  },
  radius: {
    sm: "6px",
    md: "8px",
    lg: "10px",
    xl: "12px",
    pill: "9999px",
  },
  shadow: {
    whisper: "rgba(0,0,0,0.03) 0px 4px 24px",
    micro: "rgba(16,24,40,0.04) 0px 1px 4px",
  },
  font: {
    family: "'Helvetica Neue', Helvetica, Arial, sans-serif",
    sizes: {
      micro: "10px",
      caption: "12px",
      body: "14px",
      h3: "18px",
      h2: "24px",
      h1: "32px",
    },
    weights: {
      regular: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
  },
} as const;
```

- [ ] **Step 3: `packages/renderer/src/styles/global.css`**

```css
* {
  box-sizing: border-box;
}

html, body, #root {
  margin: 0;
  padding: 0;
  height: 100vh;
  overflow: hidden;
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 14px;
  color: #101114;
  background: #ffffff;
}

button {
  font-family: inherit;
  cursor: pointer;
  border: none;
}

input, select, textarea {
  font-family: inherit;
}

table {
  border-collapse: collapse;
}

a {
  color: #7132f5;
  text-decoration: none;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-thumb {
  background: rgba(148,151,169,0.3);
  border-radius: 4px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
```

- [ ] **Step 4: Commit**

```bash
git add packages/renderer/DESIGN.md packages/renderer/src/theme.ts packages/renderer/src/styles/global.css
git commit -m "feat(renderer): add Kraken DESIGN.md, theme tokens, global CSS"
```

### Task M4.2: Sidebar component

**Files:**
- Create: `packages/renderer/src/components/Sidebar.tsx`
- Create: `packages/renderer/tests/components/Sidebar.test.tsx`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../../src/components/Sidebar.js";

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar pendingProposalCount={2} />
    </MemoryRouter>
  );
}

describe("Sidebar", () => {
  it("renders all 4 page links", () => {
    renderSidebar();
    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByText("Settings")).toBeDefined();
    expect(screen.getByText("Reports")).toBeDefined();
    expect(screen.getByText("Chat")).toBeDefined();
  });

  it("shows pending proposal count badge on Settings", () => {
    renderSidebar();
    expect(screen.getByText("2")).toBeDefined();
  });

  it("renders all 3 employee names", () => {
    renderSidebar();
    expect(screen.getByText(/Analyzer/)).toBeDefined();
    expect(screen.getByText(/Reviewer/)).toBeDefined();
    expect(screen.getByText(/Risk Mgr/)).toBeDefined();
  });
});
```

- [ ] **Step 2: Implement `packages/renderer/src/components/Sidebar.tsx`**

```typescript
import React from "react";
import { NavLink } from "react-router-dom";
import { theme } from "../theme.js";

const sidebarStyle: React.CSSProperties = {
  width: 220,
  background: theme.colors.fafafa,
  borderRight: `1px solid ${theme.colors.borderGray}`,
  padding: "24px 16px",
  flexShrink: 0,
  height: "100vh",
  overflowY: "auto",
};

const headerStyle: React.CSSProperties = {
  fontWeight: theme.font.weights.bold,
  fontSize: 20,
  letterSpacing: -0.5,
  marginBottom: 32,
  color: theme.colors.purple,
};

const sectionLabelStyle: React.CSSProperties = {
  fontSize: 12,
  textTransform: "uppercase",
  color: theme.colors.silverBlue,
  marginBottom: 12,
  fontWeight: theme.font.weights.medium,
};

interface NavItemProps {
  to: string;
  icon: string;
  label: string;
  badge?: number;
}

function NavItem({ to, icon, label, badge }: NavItemProps) {
  return (
    <NavLink
      to={to}
      style={({ isActive }) => ({
        display: "block",
        padding: "10px 12px",
        marginBottom: 4,
        borderRadius: 8,
        color: isActive ? theme.colors.purple : theme.colors.coolGray,
        background: isActive ? theme.colors.purpleSubtle : "transparent",
        fontWeight: isActive ? theme.font.weights.medium : theme.font.weights.regular,
        textDecoration: "none",
      })}
    >
      {icon} {label}
      {badge !== undefined && badge > 0 && (
        <span
          style={{
            background: theme.colors.red,
            color: theme.colors.white,
            borderRadius: 999,
            padding: "1px 6px",
            fontSize: 10,
            marginLeft: 6,
          }}
        >
          {badge}
        </span>
      )}
    </NavLink>
  );
}

interface EmployeeRowProps {
  icon: string;
  name: string;
  online: boolean;
}

function EmployeeRow({ icon, name, online }: EmployeeRowProps) {
  return (
    <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          width: 8,
          height: 8,
          background: online ? theme.colors.green : theme.colors.silverBlue,
          borderRadius: "50%",
          display: "inline-block",
        }}
      />
      {icon} {name}
    </div>
  );
}

export interface SidebarProps {
  pendingProposalCount: number;
}

export function Sidebar({ pendingProposalCount }: SidebarProps) {
  return (
    <nav style={sidebarStyle}>
      <div style={headerStyle}>Polymarket Trader</div>
      <div style={sectionLabelStyle}>Pages</div>
      <NavItem to="/" icon="📊" label="Dashboard" />
      <NavItem to="/settings" icon="⚙️" label="Settings" badge={pendingProposalCount} />
      <NavItem to="/reports" icon="📄" label="Reports" />
      <NavItem to="/chat" icon="💬" label="Chat" />

      <div style={{ ...sectionLabelStyle, marginTop: 24 }}>Employees</div>
      <EmployeeRow icon="🧠" name="Analyzer" online={true} />
      <EmployeeRow icon="📊" name="Reviewer" online={true} />
      <EmployeeRow icon="🛡️" name="Risk Mgr" online={true} />
    </nav>
  );
}
```

- [ ] **Step 3: Add react-router-dom dep**

```bash
cd packages/renderer
pnpm add react-router-dom
```

- [ ] **Step 4: Run + commit**

```bash
pnpm --filter @pmt/renderer test:run tests/components/Sidebar.test.tsx
git add packages/renderer/src/components/Sidebar.tsx packages/renderer/tests/components/Sidebar.test.tsx packages/renderer/package.json pnpm-lock.yaml
git commit -m "feat(renderer): add Sidebar with 4 page nav + 3 employee status"
```

### Task M4.3: KpiCard component

**Files:**
- Create: `packages/renderer/src/components/KpiCard.tsx`
- Create: `packages/renderer/tests/components/KpiCard.test.tsx`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { KpiCard } from "../../src/components/KpiCard.js";

describe("KpiCard", () => {
  it("renders label, value, and subtitle", () => {
    render(
      <KpiCard label="Equity" value="$10,127.50" subtitle="+$127.50 today" subtitleColor="green" />
    );
    expect(screen.getByText("Equity")).toBeDefined();
    expect(screen.getByText("$10,127.50")).toBeDefined();
    expect(screen.getByText("+$127.50 today")).toBeDefined();
  });

  it("works without subtitle", () => {
    render(<KpiCard label="Test" value="42" />);
    expect(screen.getByText("Test")).toBeDefined();
    expect(screen.getByText("42")).toBeDefined();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface KpiCardProps {
  label: string;
  value: string;
  subtitle?: string;
  subtitleColor?: "green" | "red" | "neutral";
}

const cardStyle: React.CSSProperties = {
  background: theme.colors.white,
  border: `1px solid ${theme.colors.borderGray}`,
  padding: 16,
  borderRadius: 12,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: theme.colors.silverBlue,
  textTransform: "uppercase",
  fontWeight: theme.font.weights.medium,
};

const valueStyle: React.CSSProperties = {
  fontSize: 24,
  fontWeight: theme.font.weights.bold,
  marginTop: 4,
};

export function KpiCard({ label, value, subtitle, subtitleColor }: KpiCardProps) {
  const color =
    subtitleColor === "green"
      ? theme.colors.green
      : subtitleColor === "red"
      ? theme.colors.red
      : theme.colors.coolGray;
  return (
    <div style={cardStyle}>
      <div style={labelStyle}>{label}</div>
      <div style={valueStyle}>{value}</div>
      {subtitle && (
        <div style={{ fontSize: 12, color, marginTop: 2 }}>{subtitle}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
pnpm --filter @pmt/renderer test:run tests/components/KpiCard.test.tsx
git add packages/renderer/src/components/KpiCard.tsx packages/renderer/tests/components/KpiCard.test.tsx
git commit -m "feat(renderer): add KpiCard component"
```

### Task M4.4: PositionTable component

**Files:**
- Create: `packages/renderer/src/components/PositionTable.tsx`
- Create: `packages/renderer/tests/components/PositionTable.test.tsx`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { PositionTable, type Position } from "../../src/components/PositionTable.js";

const samplePositions: Position[] = [
  {
    signalId: "s1",
    marketTitle: "Trump approval > 50%",
    side: "buy_yes",
    entryPrice: 0.452,
    currentPrice: 0.481,
    sizeUsdc: 125,
    pnl: 8.02,
    heldDuration: "42m",
  },
  {
    signalId: "s2",
    marketTitle: "BTC > $100k",
    side: "buy_yes",
    entryPrice: 0.520,
    currentPrice: 0.508,
    sizeUsdc: 108,
    pnl: -2.49,
    heldDuration: "1h 18m",
  },
];

describe("PositionTable", () => {
  it("renders all positions with market titles", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText("Trump approval > 50%")).toBeDefined();
    expect(screen.getByText("BTC > $100k")).toBeDefined();
  });

  it("shows PnL with appropriate sign", () => {
    render(<PositionTable positions={samplePositions} />);
    expect(screen.getByText(/\+\$8\.02/)).toBeDefined();
    expect(screen.getByText(/-\$2\.49/)).toBeDefined();
  });

  it("renders empty state when no positions", () => {
    render(<PositionTable positions={[]} />);
    expect(screen.getByText(/no open positions/i)).toBeDefined();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface Position {
  signalId: string;
  marketTitle: string;
  side: "buy_yes" | "buy_no";
  entryPrice: number;
  currentPrice: number;
  sizeUsdc: number;
  pnl: number;
  heldDuration: string;
}

export interface PositionTableProps {
  positions: Position[];
}

const containerStyle: React.CSSProperties = {
  background: theme.colors.white,
  border: `1px solid ${theme.colors.borderGray}`,
  borderRadius: 12,
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  padding: "16px 20px",
  borderBottom: `1px solid ${theme.colors.borderGray}`,
  fontSize: 16,
  fontWeight: theme.font.weights.semibold,
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  fontSize: 13,
};

const thStyle: React.CSSProperties = {
  background: theme.colors.fafafa,
  color: theme.colors.coolGray,
  textTransform: "uppercase",
  fontSize: 11,
  textAlign: "left",
  padding: "12px 20px",
  fontWeight: theme.font.weights.medium,
};

const tdStyle: React.CSSProperties = {
  padding: "14px 20px",
  borderTop: `1px solid ${theme.colors.rowDivider}`,
};

function SideBadge({ side }: { side: "buy_yes" | "buy_no" }) {
  const isYes = side === "buy_yes";
  return (
    <span
      style={{
        background: isYes ? theme.colors.greenSubtle : "rgba(151,107,255,0.16)",
        color: isYes ? theme.colors.greenDark : theme.colors.purpleDeep,
        padding: "3px 8px",
        borderRadius: 6,
        fontSize: 11,
        fontWeight: theme.font.weights.medium,
      }}
    >
      {isYes ? "YES" : "NO"}
    </span>
  );
}

export function PositionTable({ positions }: PositionTableProps) {
  if (positions.length === 0) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>Open Positions</div>
        <div style={{ padding: "32px 20px", textAlign: "center", color: theme.colors.silverBlue }}>
          No open positions
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Open Positions</div>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>Market</th>
            <th style={{ ...thStyle, padding: "12px" }}>Side</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>Entry</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>Now</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>Size</th>
            <th style={{ ...thStyle, padding: "12px", textAlign: "right" }}>PnL</th>
            <th style={{ ...thStyle, textAlign: "right" }}>Held</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.signalId}>
              <td style={{ ...tdStyle, fontWeight: theme.font.weights.medium }}>
                {p.marketTitle}
              </td>
              <td style={{ ...tdStyle, padding: 14 }}>
                <SideBadge side={p.side} />
              </td>
              <td style={{ ...tdStyle, padding: 14, textAlign: "right" }}>{p.entryPrice.toFixed(3)}</td>
              <td style={{ ...tdStyle, padding: 14, textAlign: "right" }}>{p.currentPrice.toFixed(3)}</td>
              <td style={{ ...tdStyle, padding: 14, textAlign: "right" }}>${p.sizeUsdc.toFixed(0)}</td>
              <td
                style={{
                  ...tdStyle,
                  padding: 14,
                  textAlign: "right",
                  color: p.pnl >= 0 ? theme.colors.green : theme.colors.red,
                  fontWeight: theme.font.weights.medium,
                }}
              >
                {p.pnl >= 0 ? "+" : ""}${p.pnl.toFixed(2)}
              </td>
              <td style={{ ...tdStyle, textAlign: "right", color: theme.colors.coolGray }}>
                {p.heldDuration}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
pnpm --filter @pmt/renderer test:run tests/components/PositionTable.test.tsx
git add packages/renderer/src/components/PositionTable.tsx packages/renderer/tests/components/PositionTable.test.tsx
git commit -m "feat(renderer): add PositionTable component"
```

### Task M4.5: CoordinatorBanner component

**Files:**
- Create: `packages/renderer/src/components/CoordinatorBanner.tsx`

- [ ] **Step 1: Implement (simple display, no test needed)**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface CoordinatorBannerProps {
  summary: string;
  generatedMinutesAgo: number;
}

export function CoordinatorBanner({ summary, generatedMinutesAgo }: CoordinatorBannerProps) {
  return (
    <div
      style={{
        background: theme.colors.purpleBg,
        borderLeft: `3px solid ${theme.colors.purple}`,
        padding: "16px 20px",
        borderRadius: 8,
        marginBottom: 24,
      }}
    >
      <div
        style={{
          fontSize: 12,
          textTransform: "uppercase",
          color: theme.colors.purpleDark,
          fontWeight: theme.font.weights.bold,
          marginBottom: 6,
        }}
      >
        🛡️ Coordinator Brief — {generatedMinutesAgo}m ago
      </div>
      <div
        style={{
          fontSize: 14,
          color: theme.colors.nearBlack,
          lineHeight: 1.5,
        }}
      >
        {summary}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/CoordinatorBanner.tsx
git commit -m "feat(renderer): add CoordinatorBanner component"
```

### Task M4.6: Dashboard page

**Files:**
- Create: `packages/renderer/src/pages/Dashboard.tsx`
- Create: `packages/renderer/src/stores/portfolio.ts`
- Create: `packages/renderer/src/stores/positions.ts`
- Create: `packages/renderer/src/stores/coordinator.ts`

- [ ] **Step 1: Add Zustand dep**

```bash
cd packages/renderer
pnpm add zustand
```

- [ ] **Step 2: Stores with mock data**

`packages/renderer/src/stores/portfolio.ts`:

```typescript
import { create } from "zustand";

export interface PortfolioState {
  equity: number;
  todayPnl: number;
  weeklyWinRate: number;
  weeklyWins: number;
  weeklyTotal: number;
  drawdownPct: number;
  peakEquity: number;
  openPositionCount: number;
  maxOpenPositions: number;
  totalExposure: number;
  refresh: () => Promise<void>;
}

export const usePortfolio = create<PortfolioState>((set) => ({
  equity: 10127.50,
  todayPnl: 127.50,
  weeklyWinRate: 0.625,
  weeklyWins: 15,
  weeklyTotal: 24,
  drawdownPct: -1.2,
  peakEquity: 10250,
  openPositionCount: 3,
  maxOpenPositions: 8,
  totalExposure: 342,
  refresh: async () => {
    // M5 will replace with real IPC call
  },
}));
```

`packages/renderer/src/stores/positions.ts`:

```typescript
import { create } from "zustand";
import type { Position } from "../components/PositionTable.js";

interface PositionsState {
  positions: Position[];
  refresh: () => Promise<void>;
}

export const usePositions = create<PositionsState>((set) => ({
  positions: [
    {
      signalId: "s1",
      marketTitle: "Trump approval > 50% by May",
      side: "buy_yes",
      entryPrice: 0.452,
      currentPrice: 0.481,
      sizeUsdc: 125,
      pnl: 8.02,
      heldDuration: "42m",
    },
    {
      signalId: "s2",
      marketTitle: "BTC > $100k by Apr 10",
      side: "buy_yes",
      entryPrice: 0.520,
      currentPrice: 0.508,
      sizeUsdc: 108,
      pnl: -2.49,
      heldDuration: "1h 18m",
    },
    {
      signalId: "s3",
      marketTitle: "Lakers vs Celtics tonight",
      side: "buy_no",
      entryPrice: 0.380,
      currentPrice: 0.395,
      sizeUsdc: 109,
      pnl: 3.81,
      heldDuration: "2h 04m",
    },
  ],
  refresh: async () => {},
}));
```

`packages/renderer/src/stores/coordinator.ts`:

```typescript
import { create } from "zustand";

interface CoordinatorState {
  latestSummary: string;
  generatedMinutesAgo: number;
  refresh: () => Promise<void>;
}

export const useCoordinator = create<CoordinatorState>((set) => ({
  latestSummary:
    "7 triggers detected in last hour, 2 entered. PnL +$8.34. Net flow on US Election markets unusually elevated — consider tightening unique_traders_1m to 4.",
  generatedMinutesAgo: 23,
  refresh: async () => {},
}));
```

- [ ] **Step 3: Implement Dashboard page**

```typescript
import React from "react";
import { theme } from "../theme.js";
import { KpiCard } from "../components/KpiCard.js";
import { PositionTable } from "../components/PositionTable.js";
import { CoordinatorBanner } from "../components/CoordinatorBanner.js";
import { usePortfolio } from "../stores/portfolio.js";
import { usePositions } from "../stores/positions.js";
import { useCoordinator } from "../stores/coordinator.js";

export function Dashboard() {
  const portfolio = usePortfolio();
  const { positions } = usePositions();
  const coordinator = useCoordinator();

  return (
    <div style={{ padding: 32, maxHeight: "100vh", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <div style={{ fontSize: 32, fontWeight: theme.font.weights.bold, letterSpacing: -1 }}>
            Dashboard
          </div>
          <div style={{ fontSize: 14, color: theme.colors.silverBlue, marginTop: 4 }}>
            {new Date().toLocaleString()}
          </div>
        </div>
        <button
          style={{
            background: theme.colors.purple,
            color: theme.colors.white,
            padding: "13px 16px",
            borderRadius: 12,
            fontWeight: theme.font.weights.medium,
            fontSize: 14,
          }}
        >
          Run Reviewer Now
        </button>
      </div>

      <CoordinatorBanner
        summary={coordinator.latestSummary}
        generatedMinutesAgo={coordinator.generatedMinutesAgo}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
        <KpiCard
          label="Equity"
          value={`$${portfolio.equity.toFixed(2)}`}
          subtitle={`+$${portfolio.todayPnl.toFixed(2)} today`}
          subtitleColor={portfolio.todayPnl >= 0 ? "green" : "red"}
        />
        <KpiCard
          label="Open positions"
          value={`${portfolio.openPositionCount} / ${portfolio.maxOpenPositions}`}
          subtitle={`Exposure $${portfolio.totalExposure}`}
        />
        <KpiCard
          label="7d Win rate"
          value={`${(portfolio.weeklyWinRate * 100).toFixed(1)}%`}
          subtitle={`${portfolio.weeklyWins} / ${portfolio.weeklyTotal} trades`}
          subtitleColor="green"
        />
        <KpiCard
          label="Drawdown"
          value={`${portfolio.drawdownPct.toFixed(1)}%`}
          subtitle={`From peak $${portfolio.peakEquity}`}
        />
      </div>

      <PositionTable positions={positions} />
    </div>
  );
}
```

- [ ] **Step 4: Build, commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/pages/Dashboard.tsx packages/renderer/src/stores/ packages/renderer/package.json pnpm-lock.yaml
git commit -m "feat(renderer): add Dashboard page with KPI cards, position table, coordinator banner"
```

### Task M4.7-M4.11: Settings page (5 tasks bundled)

The Settings page has 4 sections (LLM Providers / Trading Thresholds / Risk Limits / Pending Proposals). I'm splitting it into one section per task for review-friendly commits.

#### Task M4.7: ProviderCard component

**Files:**
- Create: `packages/renderer/src/components/ProviderCard.tsx`

- [ ] **Step 1: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface ProviderCardProps {
  name: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  authDetail?: string;
  models?: string[];
  onConnect?: () => void;
}

export function ProviderCard({
  name,
  authType,
  isConnected,
  authDetail,
  models,
  onConnect,
}: ProviderCardProps) {
  const borderColor = isConnected
    ? authType === "cli_credential" || authType === "oauth"
      ? theme.colors.green
      : theme.colors.purple
    : theme.colors.borderGray;
  const background = isConnected
    ? authType === "cli_credential" || authType === "oauth"
      ? theme.colors.greenBg
      : theme.colors.purpleBg
    : theme.colors.white;

  return (
    <div
      style={{
        border: `${isConnected ? 2 : 1}px solid ${borderColor}`,
        padding: 14,
        borderRadius: 10,
        background,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
        <div>
          <div style={{ fontWeight: theme.font.weights.semibold, fontSize: 12 }}>{name}</div>
          <div style={{ fontSize: 11, color: theme.colors.coolGray, marginTop: 2 }}>
            {authDetail ?? "Not configured"}
          </div>
        </div>
        {isConnected && (
          <div style={{ fontSize: 11, color: theme.colors.green, fontWeight: theme.font.weights.medium }}>
            ● Connected
          </div>
        )}
      </div>
      {isConnected && models && models.length > 0 && (
        <div style={{ fontSize: 11, color: theme.colors.silverBlue, marginTop: 8 }}>
          Models: {models.slice(0, 3).join(", ")}
          {models.length > 3 ? `, +${models.length - 3} more` : ""}
        </div>
      )}
      {!isConnected && onConnect && (
        <button
          onClick={onConnect}
          style={{
            background: theme.colors.purpleSubtle,
            color: theme.colors.purple,
            padding: "5px 12px",
            borderRadius: 6,
            fontSize: 11,
            marginTop: 8,
            fontWeight: theme.font.weights.medium,
          }}
        >
          + Add{authType === "oauth" ? " (OAuth)" : authType === "cli_credential" ? " (CLI)" : " key"}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/ProviderCard.tsx
git commit -m "feat(renderer): add ProviderCard component"
```

#### Task M4.8: Settings — LLM section

**Files:**
- Create: `packages/renderer/src/stores/settings.ts`
- Create: `packages/renderer/src/pages/Settings.tsx` (initial — LLM section only)

- [ ] **Step 1: settings store with mock data**

```typescript
import { create } from "zustand";

export interface ProviderInfo {
  id: string;
  name: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  authDetail?: string;
  models?: string[];
}

interface SettingsState {
  providers: ProviderInfo[];
  agentModels: {
    analyzer: { providerId: string; modelId: string };
    reviewer: { providerId: string; modelId: string };
    risk_manager: { providerId: string; modelId: string };
  };
  thresholds: {
    minTradeUsdc: number;
    minNetFlow1m: number;
    minUniqueTraders1m: number;
    minPriceMove5m: number;
    minLiquidity: number;
    deadZoneMin: number;
    deadZoneMax: number;
  };
  riskLimits: {
    totalCapital: number;
    maxPositionUsdc: number;
    maxSingleLoss: number;
    maxOpenPositions: number;
    dailyHaltPct: number;
    takeProfitPct: number;
    stopLossPct: number;
  };
  pendingProposals: Array<{
    id: number;
    field: string;
    oldValue: string;
    proposedValue: string;
    rationale: string;
    sampleCount: number;
    expectedDeltaWinrate: number;
  }>;
}

export const useSettings = create<SettingsState>(() => ({
  providers: [
    { id: "anthropic_api", name: "Anthropic", authType: "api_key", isConnected: true, authDetail: "sk-ant-...4f2a", models: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"] },
    { id: "deepseek", name: "DeepSeek", authType: "api_key", isConnected: false },
    { id: "zhipu", name: "Zhipu / Z.ai", authType: "api_key", isConnected: false },
    { id: "openai", name: "OpenAI", authType: "api_key", isConnected: false },
    { id: "anthropic_subscription", name: "Claude (Sub)", authType: "cli_credential", isConnected: true, authDetail: "Auto · Max plan · 4d left" },
    { id: "gemini_oauth", name: "Gemini (OAuth)", authType: "oauth", isConnected: true, authDetail: "Free tier · 1000/day" },
  ],
  agentModels: {
    analyzer: { providerId: "anthropic_subscription", modelId: "claude-opus-4-6" },
    reviewer: { providerId: "anthropic_subscription", modelId: "claude-sonnet-4-6" },
    risk_manager: { providerId: "gemini_oauth", modelId: "gemini-2.5-flash" },
  },
  thresholds: {
    minTradeUsdc: 200,
    minNetFlow1m: 3500,
    minUniqueTraders1m: 3,
    minPriceMove5m: 0.03,
    minLiquidity: 5000,
    deadZoneMin: 0.60,
    deadZoneMax: 0.85,
  },
  riskLimits: {
    totalCapital: 10000,
    maxPositionUsdc: 300,
    maxSingleLoss: 50,
    maxOpenPositions: 8,
    dailyHaltPct: 0.02,
    takeProfitPct: 0.10,
    stopLossPct: 0.07,
  },
  pendingProposals: [
    {
      id: 1,
      field: "min_unique_traders_1m",
      oldValue: "3",
      proposedValue: "4",
      rationale: "Bucket 0.40-0.60 win rate is 58% over 22 trades; tightening filter projected to lift to ~64%.",
      sampleCount: 22,
      expectedDeltaWinrate: 0.06,
    },
    {
      id: 2,
      field: "take_profit_pct",
      oldValue: "0.10",
      proposedValue: "0.08",
      rationale: "Past 30 trades show 70% of TP exits happen below +9%.",
      sampleCount: 30,
      expectedDeltaWinrate: 0.04,
    },
  ],
}));
```

- [ ] **Step 2: Initial Settings.tsx — LLM section only**

```typescript
import React from "react";
import { theme } from "../theme.js";
import { ProviderCard } from "../components/ProviderCard.js";
import { useSettings } from "../stores/settings.js";

export function Settings() {
  const { providers, agentModels } = useSettings();
  const apiKeyProviders = providers.filter((p) => p.authType === "api_key");
  const subscriptionProviders = providers.filter(
    (p) => p.authType === "oauth" || p.authType === "cli_credential"
  );

  return (
    <div style={{ padding: 32, maxHeight: "100vh", overflowY: "auto" }}>
      <div style={{ fontSize: 32, fontWeight: theme.font.weights.bold, letterSpacing: -1, marginBottom: 8 }}>
        Settings
      </div>
      <div style={{ fontSize: 14, color: theme.colors.silverBlue, marginBottom: 32 }}>
        Configure providers, thresholds, and review pending changes
      </div>

      {/* LLM Providers section */}
      <div
        style={{
          background: theme.colors.white,
          border: `1px solid ${theme.colors.borderGray}`,
          borderRadius: 12,
          padding: 24,
          marginBottom: 16,
        }}
      >
        <div style={{ fontSize: 18, fontWeight: theme.font.weights.semibold, marginBottom: 4 }}>
          🤖 LLM Providers
        </div>
        <div style={{ fontSize: 13, color: theme.colors.silverBlue, marginBottom: 20 }}>
          Configure API keys and per-agent model overrides
        </div>

        <div style={{ fontSize: 11, textTransform: "uppercase", color: theme.colors.silverBlue, fontWeight: theme.font.weights.bold, marginBottom: 10 }}>
          API Key
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
          {apiKeyProviders.map((p) => (
            <ProviderCard
              key={p.id}
              name={p.name}
              authType={p.authType}
              isConnected={p.isConnected}
              authDetail={p.authDetail}
              models={p.models}
            />
          ))}
        </div>

        <div style={{ fontSize: 11, textTransform: "uppercase", color: theme.colors.silverBlue, fontWeight: theme.font.weights.bold, marginBottom: 10, borderTop: `1px dashed ${theme.colors.borderGray}`, paddingTop: 16 }}>
          ↓ Subscription / OAuth
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
          {subscriptionProviders.map((p) => (
            <ProviderCard
              key={p.id}
              name={p.name}
              authType={p.authType}
              isConnected={p.isConnected}
              authDetail={p.authDetail}
            />
          ))}
        </div>

        <div style={{ fontSize: 11, textTransform: "uppercase", color: theme.colors.silverBlue, fontWeight: theme.font.weights.bold, marginBottom: 12, borderTop: `1px dashed ${theme.colors.borderGray}`, paddingTop: 16 }}>
          Per-agent model assignment
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          {(["analyzer", "reviewer", "risk_manager"] as const).map((agentId) => {
            const assignment = agentModels[agentId];
            const labels: Record<typeof agentId, string> = {
              analyzer: "🧠 Analyzer",
              reviewer: "📊 Reviewer",
              risk_manager: "🛡️ Risk Mgr",
            };
            return (
              <div key={agentId}>
                <div style={{ fontSize: 13, color: theme.colors.coolGray, marginBottom: 4 }}>
                  {labels[agentId]}
                </div>
                <div
                  style={{
                    border: `1px solid ${theme.colors.borderGray}`,
                    padding: "10px 12px",
                    borderRadius: 8,
                    fontSize: 13,
                  }}
                >
                  <div style={{ fontWeight: theme.font.weights.medium }}>{assignment.modelId}</div>
                  <div style={{ fontSize: 10, color: theme.colors.green, marginTop: 2 }}>
                    via {assignment.providerId}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Build, commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/pages/Settings.tsx packages/renderer/src/stores/settings.ts
git commit -m "feat(renderer): add Settings page LLM section with provider cards"
```

#### Task M4.9: Settings — Trading thresholds section

- [ ] **Step 1: Append the thresholds section to `Settings.tsx`** (between LLM section and end of return)

```typescript
{/* Trading Thresholds section */}
<div
  style={{
    background: theme.colors.white,
    border: `1px solid ${theme.colors.borderGray}`,
    borderRadius: 12,
    padding: 24,
    marginBottom: 16,
  }}
>
  <div style={{ fontSize: 18, fontWeight: theme.font.weights.semibold, marginBottom: 4 }}>
    ⚡ Trading Thresholds
  </div>
  <div style={{ fontSize: 13, color: theme.colors.silverBlue, marginBottom: 20 }}>
    When to trigger a signal
  </div>
  <table style={{ width: "100%", fontSize: 13 }}>
    <tbody>
      {[
        { label: "Min trade size", value: `$${useSettings.getState().thresholds.minTradeUsdc}`, locked: false },
        { label: "Min net flow (1m)", value: `$${useSettings.getState().thresholds.minNetFlow1m}`, locked: false, autoApplied: true },
        { label: "Min unique traders (1m)", value: `${useSettings.getState().thresholds.minUniqueTraders1m}`, locked: false },
        { label: "Min price move (5m)", value: `${(useSettings.getState().thresholds.minPriceMove5m * 100).toFixed(1)}%`, locked: false },
        { label: "Min liquidity", value: `$${useSettings.getState().thresholds.minLiquidity}`, locked: false },
        { label: "Dead zone", value: `[${useSettings.getState().thresholds.deadZoneMin}, ${useSettings.getState().thresholds.deadZoneMax}]`, locked: true },
      ].map((row) => (
        <tr key={row.label} style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
          <td style={{ padding: "10px 0", color: theme.colors.coolGray }}>{row.label}</td>
          <td style={{ textAlign: "right", fontWeight: theme.font.weights.medium }}>
            {row.value}
            {row.autoApplied && (
              <span style={{ background: theme.colors.greenSubtle, color: theme.colors.greenDark, padding: "2px 6px", borderRadius: 4, fontSize: 10, marginLeft: 6 }}>
                auto-applied
              </span>
            )}
          </td>
          <td style={{ textAlign: "right", width: 80 }}>
            {row.locked ? (
              <span style={{ color: theme.colors.silverBlue, fontSize: 12 }}>locked</span>
            ) : (
              <span style={{ color: theme.colors.purple, fontSize: 12, cursor: "pointer" }}>edit</span>
            )}
          </td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

- [ ] **Step 2: Build + commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/pages/Settings.tsx
git commit -m "feat(renderer): add Settings trading thresholds section"
```

#### Task M4.10: ProposalCard component

**Files:**
- Create: `packages/renderer/src/components/ProposalCard.tsx`

- [ ] **Step 1: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface ProposalCardProps {
  field: string;
  oldValue: string;
  proposedValue: string;
  rationale: string;
  onApprove: () => void;
  onReject: () => void;
}

export function ProposalCard({ field, oldValue, proposedValue, rationale, onApprove, onReject }: ProposalCardProps) {
  return (
    <div
      style={{
        border: `1px solid ${theme.colors.borderGray}`,
        borderRadius: 10,
        padding: 16,
        marginBottom: 12,
      }}
    >
      <div style={{ fontWeight: theme.font.weights.medium }}>
        {field}: <span style={{ textDecoration: "line-through", color: theme.colors.silverBlue }}>{oldValue}</span>
        {" → "}
        <strong>{proposedValue}</strong>
      </div>
      <div style={{ fontSize: 12, color: theme.colors.coolGray, margin: "6px 0" }}>{rationale}</div>
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button
          onClick={onApprove}
          style={{
            background: theme.colors.purple,
            color: theme.colors.white,
            padding: "8px 14px",
            borderRadius: 8,
            fontSize: 12,
            fontWeight: theme.font.weights.medium,
          }}
        >
          Approve
        </button>
        <button
          onClick={onReject}
          style={{
            background: "rgba(148,151,169,0.08)",
            color: theme.colors.nearBlack,
            padding: "8px 14px",
            borderRadius: 8,
            fontSize: 12,
            fontWeight: theme.font.weights.medium,
          }}
        >
          Reject
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/ProposalCard.tsx
git commit -m "feat(renderer): add ProposalCard component"
```

#### Task M4.11: Settings — Risk Limits + Pending Proposals sections

- [ ] **Step 1: Append both sections to Settings.tsx**

After the Trading Thresholds section, add:

```typescript
{/* Risk Limits section */}
<div
  style={{
    background: theme.colors.white,
    border: `1px solid ${theme.colors.borderGray}`,
    borderRadius: 12,
    padding: 24,
    marginBottom: 16,
  }}
>
  <div style={{ fontSize: 18, fontWeight: theme.font.weights.semibold, marginBottom: 4 }}>
    🛡️ Risk Limits
  </div>
  <div style={{ fontSize: 13, color: theme.colors.silverBlue, marginBottom: 20 }}>
    Hard caps on capital and exits
  </div>
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 13 }}>
    {[
      ["Total capital", `$${useSettings.getState().riskLimits.totalCapital.toLocaleString()}`],
      ["Max position size", `$${useSettings.getState().riskLimits.maxPositionUsdc}`],
      ["Max single-trade loss", `$${useSettings.getState().riskLimits.maxSingleLoss}`],
      ["Max open positions", `${useSettings.getState().riskLimits.maxOpenPositions}`],
      ["Daily halt threshold", `${(useSettings.getState().riskLimits.dailyHaltPct * 100).toFixed(1)}%`],
      ["Take profit / Stop loss", `+${(useSettings.getState().riskLimits.takeProfitPct * 100).toFixed(0)}% / -${(useSettings.getState().riskLimits.stopLossPct * 100).toFixed(0)}%`],
    ].map(([label, value]) => (
      <div key={label}>
        <div style={{ color: theme.colors.coolGray }}>{label}</div>
        <div style={{ fontWeight: theme.font.weights.semibold, fontSize: 16 }}>{value}</div>
      </div>
    ))}
  </div>
</div>

{/* Pending Proposals section */}
<div
  style={{
    background: theme.colors.white,
    border: `2px solid ${theme.colors.purple}`,
    borderRadius: 12,
    padding: 24,
  }}
>
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
    <div style={{ fontSize: 18, fontWeight: theme.font.weights.semibold }}>
      📝 Pending Filter Proposals ({useSettings.getState().pendingProposals.length})
    </div>
    <div style={{ fontSize: 12, color: theme.colors.silverBlue }}>From Reviewer</div>
  </div>
  <div style={{ fontSize: 13, color: theme.colors.silverBlue, marginBottom: 16 }}>
    Reviewer's data-driven suggestions awaiting your approval
  </div>
  {useSettings.getState().pendingProposals.map((p) => (
    <ProposalCard
      key={p.id}
      field={p.field}
      oldValue={p.oldValue}
      proposedValue={p.proposedValue}
      rationale={p.rationale}
      onApprove={() => console.log("approve", p.id)}
      onReject={() => console.log("reject", p.id)}
    />
  ))}
</div>
```

- [ ] **Step 2: Add `import { ProposalCard }` at top of Settings.tsx**

- [ ] **Step 3: Build + commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/pages/Settings.tsx
git commit -m "feat(renderer): add Settings risk limits and pending proposals sections"
```

### Task M4.12: ReportListItem component

**Files:**
- Create: `packages/renderer/src/components/ReportListItem.tsx`

- [ ] **Step 1: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface ReportListItemProps {
  date: string;
  period: "daily" | "weekly";
  tradeCount: number;
  netPnl: number;
  isSelected: boolean;
  onClick: () => void;
}

export function ReportListItem({ date, period, tradeCount, netPnl, isSelected, onClick }: ReportListItemProps) {
  const pnlColor = netPnl >= 0 ? theme.colors.green : theme.colors.red;
  return (
    <div
      onClick={onClick}
      style={{
        background: isSelected ? theme.colors.purpleSubtle : "transparent",
        color: isSelected ? theme.colors.purple : "inherit",
        padding: "12px 14px",
        borderRadius: 8,
        marginBottom: 4,
        cursor: "pointer",
      }}
    >
      <div style={{ fontWeight: isSelected ? theme.font.weights.semibold : theme.font.weights.medium, fontSize: 13 }}>
        {date}
      </div>
      <div style={{ fontSize: 11, marginTop: 2, color: isSelected ? theme.colors.purple : pnlColor }}>
        {period === "weekly" ? "Weekly" : "Daily"} · {tradeCount} trades · {netPnl >= 0 ? "+" : ""}${netPnl.toFixed(2)}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/ReportListItem.tsx
git commit -m "feat(renderer): add ReportListItem component"
```

### Task M4.13: BucketTable component

**Files:**
- Create: `packages/renderer/src/components/BucketTable.tsx`

- [ ] **Step 1: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface BucketRow {
  bucket: number;
  trades: number;
  wins: number;
  winRate: number;
  netPnl: number;
}

export interface BucketTableProps {
  rows: BucketRow[];
}

export function BucketTable({ rows }: BucketTableProps) {
  return (
    <table style={{ width: "100%", fontSize: 13 }}>
      <thead>
        <tr style={{ background: theme.colors.fafafa, fontSize: 11, textTransform: "uppercase", color: theme.colors.coolGray }}>
          <th style={{ textAlign: "left", padding: 10 }}>Bucket</th>
          <th style={{ textAlign: "right", padding: 10 }}>Trades</th>
          <th style={{ textAlign: "right", padding: 10 }}>Wins</th>
          <th style={{ textAlign: "right", padding: 10 }}>Win rate</th>
          <th style={{ textAlign: "right", padding: 10 }}>Net PnL</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.bucket} style={{ borderBottom: `1px solid ${theme.colors.rowDivider}` }}>
            <td style={{ padding: 10 }}>{r.bucket.toFixed(2)}</td>
            <td style={{ padding: 10, textAlign: "right" }}>{r.trades}</td>
            <td style={{ padding: 10, textAlign: "right" }}>{r.wins}</td>
            <td style={{ padding: 10, textAlign: "right" }}>{(r.winRate * 100).toFixed(1)}%</td>
            <td
              style={{
                padding: 10,
                textAlign: "right",
                color: r.netPnl >= 0 ? theme.colors.green : theme.colors.red,
              }}
            >
              {r.netPnl >= 0 ? "+" : ""}${r.netPnl.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/BucketTable.tsx
git commit -m "feat(renderer): add BucketTable component"
```

### Task M4.14: Reports page

**Files:**
- Create: `packages/renderer/src/pages/Reports.tsx`

- [ ] **Step 1: Implement Reports.tsx with mock report list**

```typescript
import React, { useState } from "react";
import { theme } from "../theme.js";
import { ReportListItem } from "../components/ReportListItem.js";
import { BucketTable, type BucketRow } from "../components/BucketTable.js";

interface MockReport {
  id: string;
  date: string;
  period: "daily" | "weekly";
  tradeCount: number;
  netPnl: number;
  totalPnl7d: number;
  winRate: number;
  weeklyWins: number;
  weeklyTotal: number;
  sharpe: number;
  buckets: BucketRow[];
  notes: string;
  proposals: Array<{ kind: "auto" | "pending"; field: string; change: string }>;
}

const MOCK_REPORTS: MockReport[] = [
  {
    id: "2026-04-06",
    date: "Apr 6, 2026",
    period: "weekly",
    tradeCount: 24,
    netPnl: 127.50,
    totalPnl7d: 127.50,
    winRate: 0.625,
    weeklyWins: 15,
    weeklyTotal: 24,
    sharpe: 1.42,
    buckets: [
      { bucket: 0.30, trades: 3, wins: 2, winRate: 0.667, netPnl: 24.10 },
      { bucket: 0.40, trades: 7, wins: 5, winRate: 0.714, netPnl: 56.20 },
      { bucket: 0.45, trades: 9, wins: 5, winRate: 0.556, netPnl: 31.40 },
      { bucket: 0.50, trades: 4, wins: 2, winRate: 0.500, netPnl: 15.80 },
      { bucket: 0.85, trades: 1, wins: 1, winRate: 1.0, netPnl: 0 },
    ],
    notes: "Strong week. Bucket 0.40-0.45 was the standout performer (71% win rate). One concerning pattern: 4 of 9 losses hit the time-stop instead of stop loss.",
    proposals: [
      { kind: "auto", field: "min_net_flow_1m", change: "3000 → 3500" },
      { kind: "pending", field: "min_unique_traders_1m", change: "3 → 4" },
      { kind: "pending", field: "take_profit_pct", change: "0.10 → 0.08" },
    ],
  },
  { id: "2026-04-05", date: "Apr 5, 2026", period: "daily", tradeCount: 4, netPnl: 18.20, totalPnl7d: 0, winRate: 0, weeklyWins: 0, weeklyTotal: 0, sharpe: 0, buckets: [], notes: "", proposals: [] },
  { id: "2026-04-04", date: "Apr 4, 2026", period: "daily", tradeCount: 3, netPnl: -8.40, totalPnl7d: 0, winRate: 0, weeklyWins: 0, weeklyTotal: 0, sharpe: 0, buckets: [], notes: "", proposals: [] },
];

export function Reports() {
  const [selectedId, setSelectedId] = useState(MOCK_REPORTS[0]!.id);
  const selected = MOCK_REPORTS.find((r) => r.id === selectedId)!;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      {/* Report list */}
      <div style={{ width: 280, borderRight: `1px solid ${theme.colors.borderGray}`, padding: "20px 0", overflowY: "auto" }}>
        <div style={{ padding: "0 20px 16px" }}>
          <div style={{ fontSize: 24, fontWeight: theme.font.weights.bold, letterSpacing: -0.5 }}>Reports</div>
          <div style={{ fontSize: 12, color: theme.colors.silverBlue, marginTop: 4 }}>Reviewer history</div>
        </div>
        <div style={{ padding: "0 20px" }}>
          {MOCK_REPORTS.map((r) => (
            <ReportListItem
              key={r.id}
              date={r.date}
              period={r.period}
              tradeCount={r.tradeCount}
              netPnl={r.netPnl}
              isSelected={r.id === selectedId}
              onClick={() => setSelectedId(r.id)}
            />
          ))}
        </div>
      </div>

      {/* Report content */}
      <div style={{ flex: 1, padding: 32, overflowY: "auto" }}>
        <div style={{ fontSize: 24, fontWeight: theme.font.weights.bold, letterSpacing: -0.5 }}>
          {selected.period === "weekly" ? "Weekly Review" : "Daily Review"} · {selected.date}
        </div>
        <div style={{ fontSize: 13, color: theme.colors.silverBlue, marginTop: 4, marginBottom: 24 }}>
          Generated by Reviewer · claude-sonnet-4-6
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 24 }}>
          <div style={{ background: theme.colors.greenBg, border: `1px solid rgba(20,158,97,0.2)`, padding: 14, borderRadius: 10 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", color: theme.colors.coolGray, fontWeight: theme.font.weights.medium }}>
              7d Net PnL
            </div>
            <div style={{ fontSize: 20, fontWeight: theme.font.weights.bold, color: theme.colors.green, marginTop: 4 }}>
              {selected.totalPnl7d >= 0 ? "+" : ""}${selected.totalPnl7d.toFixed(2)}
            </div>
          </div>
          <div style={{ background: theme.colors.white, border: `1px solid ${theme.colors.borderGray}`, padding: 14, borderRadius: 10 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", color: theme.colors.coolGray, fontWeight: theme.font.weights.medium }}>
              Win rate
            </div>
            <div style={{ fontSize: 20, fontWeight: theme.font.weights.bold, marginTop: 4 }}>
              {(selected.winRate * 100).toFixed(1)}%
            </div>
            <div style={{ fontSize: 11, color: theme.colors.coolGray }}>
              {selected.weeklyWins} / {selected.weeklyTotal} trades
            </div>
          </div>
          <div style={{ background: theme.colors.white, border: `1px solid ${theme.colors.borderGray}`, padding: 14, borderRadius: 10 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", color: theme.colors.coolGray, fontWeight: theme.font.weights.medium }}>
              Sharpe
            </div>
            <div style={{ fontSize: 20, fontWeight: theme.font.weights.bold, marginTop: 4 }}>{selected.sharpe.toFixed(2)}</div>
          </div>
        </div>

        <h3 style={{ fontSize: 18, fontWeight: theme.font.weights.semibold, margin: "24px 0 12px" }}>
          Per-bucket performance
        </h3>
        <BucketTable rows={selected.buckets} />

        <h3 style={{ fontSize: 18, fontWeight: theme.font.weights.semibold, margin: "24px 0 12px" }}>
          Notes from Reviewer
        </h3>
        <div style={{ background: theme.colors.fafafa, padding: 16, borderRadius: 8, fontSize: 13, lineHeight: 1.6 }}>
          {selected.notes || "(no notes)"}
        </div>

        <h3 style={{ fontSize: 18, fontWeight: theme.font.weights.semibold, margin: "24px 0 12px" }}>
          Filter proposals
        </h3>
        <ul style={{ fontSize: 13 }}>
          {selected.proposals.map((p, i) => (
            <li key={i}>
              <strong>{p.kind === "auto" ? "Auto-applied" : "Pending review"}</strong>:{" "}
              <code>{p.field}</code> {p.change}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build + commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/pages/Reports.tsx
git commit -m "feat(renderer): add Reports page with list + detail layout"
```

### Task M4.15-M4.18: Chat page (4 sub-tasks)

#### Task M4.15: ChatMessage component

**Files:**
- Create: `packages/renderer/src/components/ChatMessage.tsx`

- [ ] **Step 1: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface ChatMessageProps {
  role: "user" | "assistant" | "system";
  content: string;
  agentIcon?: string;
}

export function ChatMessage({ role, content, agentIcon }: ChatMessageProps) {
  if (role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <div
          style={{
            maxWidth: "70%",
            background: theme.colors.purple,
            color: theme.colors.white,
            padding: "12px 16px",
            borderRadius: "16px 16px 4px 16px",
            fontSize: 14,
            lineHeight: 1.4,
          }}
        >
          {content}
        </div>
      </div>
    );
  }

  if (role === "system") {
    return (
      <div
        style={{
          background: theme.colors.purpleBg,
          borderLeft: `3px solid ${theme.colors.purple}`,
          padding: "12px 16px",
          borderRadius: 8,
          marginBottom: 20,
          fontSize: 13,
          color: theme.colors.nearBlack,
        }}
      >
        {content}
      </div>
    );
  }

  // assistant
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: theme.colors.purpleSubtle,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 16,
          flexShrink: 0,
        }}
      >
        {agentIcon ?? "🤖"}
      </div>
      <div
        style={{
          maxWidth: "80%",
          background: theme.colors.white,
          border: `1px solid ${theme.colors.borderGray}`,
          padding: "14px 18px",
          borderRadius: "4px 16px 16px 16px",
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
        }}
      >
        {content}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/ChatMessage.tsx
git commit -m "feat(renderer): add ChatMessage component (user/assistant/system styles)"
```

#### Task M4.16: ChatInput component

**Files:**
- Create: `packages/renderer/src/components/ChatInput.tsx`

- [ ] **Step 1: Implement**

```typescript
import React, { useState } from "react";
import { theme } from "../theme.js";

export interface ChatInputProps {
  placeholder: string;
  helpText?: string;
  onSend: (text: string) => void;
}

export function ChatInput({ placeholder, helpText, onSend }: ChatInputProps) {
  const [text, setText] = useState("");

  function handleSend() {
    if (text.trim().length === 0) return;
    onSend(text.trim());
    setText("");
  }

  return (
    <div style={{ padding: "16px 24px", borderTop: `1px solid ${theme.colors.borderGray}` }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={placeholder}
          style={{
            flex: 1,
            border: `1px solid ${theme.colors.borderGray}`,
            padding: "12px 16px",
            borderRadius: 12,
            fontSize: 14,
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          style={{
            background: theme.colors.purple,
            color: theme.colors.white,
            padding: "12px 18px",
            borderRadius: 12,
            fontWeight: theme.font.weights.medium,
          }}
        >
          Send
        </button>
      </div>
      {helpText && (
        <div style={{ fontSize: 11, color: theme.colors.silverBlue, marginTop: 8 }}>{helpText}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/ChatInput.tsx
git commit -m "feat(renderer): add ChatInput component"
```

#### Task M4.17: EmployeeTab component

**Files:**
- Create: `packages/renderer/src/components/EmployeeTab.tsx`

- [ ] **Step 1: Implement**

```typescript
import React from "react";
import { theme } from "../theme.js";

export interface EmployeeTabProps {
  icon: string;
  isActive: boolean;
  onClick: () => void;
}

export function EmployeeTab({ icon, isActive, onClick }: EmployeeTabProps) {
  return (
    <div
      onClick={onClick}
      style={{
        width: 44,
        height: 44,
        borderRadius: 12,
        background: isActive ? theme.colors.purple : "rgba(148,151,169,0.08)",
        boxShadow: isActive ? theme.shadow.whisper : undefined,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 22,
        color: isActive ? theme.colors.white : "inherit",
        cursor: "pointer",
      }}
    >
      {icon}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/components/EmployeeTab.tsx
git commit -m "feat(renderer): add EmployeeTab component"
```

#### Task M4.18: Chat page

**Files:**
- Create: `packages/renderer/src/pages/Chat.tsx`
- Create: `packages/renderer/src/stores/chat.ts`

- [ ] **Step 1: chat store**

```typescript
import { create } from "zustand";

export type AgentId = "analyzer" | "reviewer" | "risk_manager";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
}

interface ChatState {
  activeAgent: AgentId;
  setActiveAgent: (agent: AgentId) => void;
  messagesByAgent: Record<AgentId, ChatMessage[]>;
  appendMessage: (agent: AgentId, msg: Omit<ChatMessage, "id" | "timestamp">) => void;
}

let nextId = 1;

export const useChat = create<ChatState>((set) => ({
  activeAgent: "risk_manager",
  setActiveAgent: (agent) => set({ activeAgent: agent }),
  messagesByAgent: {
    analyzer: [],
    reviewer: [],
    risk_manager: [
      {
        id: nextId++,
        role: "system",
        content:
          "⏰ Coordinator brief · auto-generated 23 min ago\n\n7 triggers detected in past hour, 2 entered (BTC YES, Lakers NO). Net flow on US Election markets unusually elevated.",
        timestamp: Date.now() - 23 * 60_000,
      },
      {
        id: nextId++,
        role: "user",
        content: "Are we close to any halts? What's our drawdown right now?",
        timestamp: Date.now() - 5 * 60_000,
      },
      {
        id: nextId++,
        role: "assistant",
        content:
          "Currently safe on all halts:\n\n- Daily DD: -0.8% (halt at -2.0%)\n- Weekly DD: -1.5% (halt at -4.0%)\n- Total DD from peak: -1.2%\n\nRisk budget: $94.50 remaining today.",
        timestamp: Date.now() - 4 * 60_000,
      },
    ],
  },
  appendMessage: (agent, msg) =>
    set((state) => ({
      messagesByAgent: {
        ...state.messagesByAgent,
        [agent]: [
          ...state.messagesByAgent[agent],
          { ...msg, id: nextId++, timestamp: Date.now() },
        ],
      },
    })),
}));
```

- [ ] **Step 2: Chat.tsx**

```typescript
import React from "react";
import { theme } from "../theme.js";
import { ChatMessage } from "../components/ChatMessage.js";
import { ChatInput } from "../components/ChatInput.js";
import { EmployeeTab } from "../components/EmployeeTab.js";
import { useChat, type AgentId } from "../stores/chat.js";

const AGENTS: Array<{ id: AgentId; icon: string; name: string; model: string }> = [
  { id: "analyzer", icon: "🧠", name: "Analyzer", model: "claude-opus-4-6" },
  { id: "reviewer", icon: "📊", name: "Reviewer", model: "claude-sonnet-4-6" },
  { id: "risk_manager", icon: "🛡️", name: "Risk Manager", model: "gemini-2.5-flash" },
];

export function Chat() {
  const { activeAgent, setActiveAgent, messagesByAgent, appendMessage } = useChat();
  const messages = messagesByAgent[activeAgent];
  const agent = AGENTS.find((a) => a.id === activeAgent)!;

  function handleSend(text: string) {
    appendMessage(activeAgent, { role: "user", content: text });
    // M5 will replace this mock with real IPC streaming
    setTimeout(() => {
      appendMessage(activeAgent, {
        role: "assistant",
        content: "(Mock reply — real IPC wiring comes in M5.)",
      });
    }, 500);
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      {/* Employee tabs */}
      <div
        style={{
          width: 60,
          background: theme.colors.fafafa,
          borderRight: `1px solid ${theme.colors.borderGray}`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "20px 0",
          gap: 16,
        }}
      >
        {AGENTS.map((a) => (
          <EmployeeTab
            key={a.id}
            icon={a.icon}
            isActive={activeAgent === a.id}
            onClick={() => setActiveAgent(a.id)}
          />
        ))}
      </div>

      {/* Conversation */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <div
          style={{
            padding: "16px 24px",
            borderBottom: `1px solid ${theme.colors.borderGray}`,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: theme.colors.purpleSubtle,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
            }}
          >
            {agent.icon}
          </div>
          <div>
            <div style={{ fontWeight: theme.font.weights.semibold, fontSize: 15 }}>{agent.name}</div>
            <div style={{ fontSize: 11, color: theme.colors.green }}>● Online · {agent.model}</div>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, padding: 24, overflowY: "auto", background: "#fdfdfd" }}>
          {messages.map((m) => (
            <ChatMessage
              key={m.id}
              role={m.role}
              content={m.content}
              agentIcon={agent.icon}
            />
          ))}
        </div>

        <ChatInput
          placeholder={`Ask ${agent.name}...`}
          helpText={
            activeAgent === "risk_manager"
              ? "Risk Mgr can read: portfolio_state, signal_log, strategy_performance · Cannot modify config"
              : undefined
          }
          onSend={handleSend}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Build + commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/pages/Chat.tsx packages/renderer/src/stores/chat.ts
git commit -m "feat(renderer): add Chat page with 3 employee tabs and message stream"
```

### Task M4.19: App.tsx with React Router and sidebar layout

**Files:**
- Modify: `packages/renderer/src/main.tsx` (replace placeholder)
- Create: `packages/renderer/src/App.tsx`

- [ ] **Step 1: App.tsx**

```typescript
import React from "react";
import { BrowserRouter, HashRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar.js";
import { Dashboard } from "./pages/Dashboard.js";
import { Settings } from "./pages/Settings.js";
import { Reports } from "./pages/Reports.js";
import { Chat } from "./pages/Chat.js";
import { useSettings } from "./stores/settings.js";

export function App() {
  const pendingProposalCount = useSettings.getState().pendingProposals.length;

  return (
    <HashRouter>
      <div style={{ display: "flex", height: "100vh" }}>
        <Sidebar pendingProposalCount={pendingProposalCount} />
        <div style={{ flex: 1, overflow: "hidden" }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/chat" element={<Chat />} />
          </Routes>
        </div>
      </div>
    </HashRouter>
  );
}
```

Note: HashRouter (not BrowserRouter) is used because Electron's `file://` protocol doesn't support history API routes.

- [ ] **Step 2: Replace `packages/renderer/src/main.tsx`**

```typescript
import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.js";
import "./styles/global.css";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<App />);
}

export const PACKAGE_NAME = "@pmt/renderer";
```

- [ ] **Step 3: Build + manual smoke**

```bash
pnpm --filter @pmt/renderer build
pnpm --filter @pmt/renderer dev   # opens at http://localhost:5173
```

Manually verify each page renders.

- [ ] **Step 4: Commit**

```bash
git add packages/renderer/src/App.tsx packages/renderer/src/main.tsx
git commit -m "feat(renderer): wire App.tsx with React Router and 4 page routes"
```

### Task M4.20: Run M4 verification gate

- [ ] **Step 1: Run renderer tests**

```bash
pnpm --filter @pmt/renderer test:run
```

Expected: ~10-15 component tests pass.

- [ ] **Step 2: Build all packages**

```bash
cd D:/work/polymarket-trader
pnpm build
```

- [ ] **Step 3: Type-check**

```bash
pnpm typecheck
```

- [ ] **Step 4: Run renderer dev server and visually verify all 4 pages**

```bash
pnpm --filter @pmt/renderer dev
```

Open http://localhost:5173 and click through Dashboard / Settings / Reports / Chat. Each should render with mock data matching the brainstorm mockups.

- [ ] **Step 5: Commit any visual fixes**

If anything looks off, fix and commit. Otherwise no commit needed.

---

## M4 Verification Gate

- [ ] All 20 M4 tasks complete
- [ ] All 4 pages render with mock data
- [ ] Sidebar nav works (clicking switches pages)
- [ ] Visual style matches Kraken DESIGN.md and brainstorm mockups
- [ ] All renderer tests pass
- [ ] All packages build cleanly

---

## M5 — IPC Wiring (~15 tasks)

Goal: Replace mock Zustand state with real IPC calls. After M5 the UI shows REAL data from the engine: real positions from `signal_log`, real PnL from `portfolio_state`, real chats invoke real LLM via `@pmt/llm`. Streaming chat works.

### Task M5.1: IPC handler module skeleton

**Files:**
- Create: `packages/main/src/ipc.ts`
- Create: `packages/main/tests/ipc.test.ts`

- [ ] **Step 1: Test (handler registration smoke)**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { registerIpcHandlers } from "../src/ipc.js";

const mockIpcMain = {
  handle: vi.fn(),
  on: vi.fn(),
};

vi.mock("electron", () => ({
  ipcMain: mockIpcMain,
}));

describe("registerIpcHandlers", () => {
  beforeEach(() => {
    mockIpcMain.handle.mockClear();
  });

  it("registers all expected request/response handlers", () => {
    registerIpcHandlers({
      getEngineContext: () => null as any,
      getRiskMgrRunner: () => null as any,
    });
    const registered = mockIpcMain.handle.mock.calls.map((c) => c[0]);
    expect(registered).toContain("getPortfolioState");
    expect(registered).toContain("getOpenPositions");
    expect(registered).toContain("getRecentClosedTrades");
    expect(registered).toContain("getLatestCoordinatorBrief");
    expect(registered).toContain("getRecentReports");
    expect(registered).toContain("getPendingProposals");
    expect(registered).toContain("approveProposal");
    expect(registered).toContain("rejectProposal");
    expect(registered).toContain("getConfig");
    expect(registered).toContain("updateConfigField");
    expect(registered).toContain("listProviders");
    expect(registered).toContain("connectProvider");
    expect(registered).toContain("disconnectProvider");
    expect(registered).toContain("setAgentModel");
    expect(registered).toContain("getChatHistory");
    expect(registered).toContain("sendMessage");
    expect(registered).toContain("clearChatHistory");
    expect(registered).toContain("pauseTrading");
    expect(registered).toContain("resumeTrading");
    expect(registered).toContain("emergencyStop");
    expect(registered).toContain("triggerReviewerNow");
    expect(registered).toContain("triggerCoordinatorNow");
  });
});
```

- [ ] **Step 2: Implement `packages/main/src/ipc.ts`** (skeleton — handler bodies stub for now, real bodies in M5.2-M5.10)

```typescript
import { ipcMain } from "electron";
import type { EngineContext } from "./lifecycle.js";
import type { RiskMgrRunner } from "@pmt/llm";

export interface IpcDeps {
  getEngineContext: () => EngineContext | null;
  getRiskMgrRunner: () => RiskMgrRunner | null;
}

export function registerIpcHandlers(deps: IpcDeps): void {
  // Portfolio
  ipcMain.handle("getPortfolioState", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    const rows = ctx.db
      .prepare("SELECT key, value FROM portfolio_state")
      .all() as Array<{ key: string; value: string }>;
    return Object.fromEntries(rows.map((r) => [r.key, JSON.parse(r.value)]));
  });

  ipcMain.handle("getOpenPositions", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db.prepare("SELECT * FROM signal_log WHERE exit_at IS NULL").all();
  });

  ipcMain.handle("getRecentClosedTrades", async (_e, limit: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare("SELECT * FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT ?")
      .all(limit);
  });

  // Coordinator
  ipcMain.handle("getLatestCoordinatorBrief", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    return ctx.db
      .prepare("SELECT * FROM coordinator_log ORDER BY generated_at DESC LIMIT 1")
      .get();
  });

  ipcMain.handle("triggerCoordinatorNow", async () => {
    // M5.6 will wire this to the scheduler.triggerNow()
    return null;
  });

  // Reports
  ipcMain.handle("getRecentReports", async (_e, limit: number) => {
    // M5.7 will list reports from filesystem
    return [];
  });

  ipcMain.handle("getReportContent", async (_e, reportPath: string) => {
    // M5.7
    return "";
  });

  ipcMain.handle("triggerReviewerNow", async () => {
    // M5.6
    return null;
  });

  // Filter proposals
  ipcMain.handle("getPendingProposals", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare("SELECT * FROM filter_proposals WHERE status = 'pending' ORDER BY created_at DESC")
      .all();
  });

  ipcMain.handle("approveProposal", async (_e, id: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    // M5.8 will apply the proposal to filter_config and mark approved
    ctx.db
      .prepare("UPDATE filter_proposals SET status = 'approved', reviewed_at = ? WHERE proposal_id = ?")
      .run(Date.now(), id);
  });

  ipcMain.handle("rejectProposal", async (_e, id: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.db
      .prepare("UPDATE filter_proposals SET status = 'rejected', reviewed_at = ? WHERE proposal_id = ?")
      .run(Date.now(), id);
  });

  // Config
  ipcMain.handle("getConfig", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return null;
    return ctx.config;
  });

  ipcMain.handle("updateConfigField", async (_e, key: string, value: unknown) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.db
      .prepare("INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source")
      .run(key, JSON.stringify(value), Date.now(), "user");
  });

  // LLM Providers
  ipcMain.handle("listProviders", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.registry.list().map((p) => ({
      providerId: p.id,
      displayName: p.displayName,
      authType: p.authType,
      isConnected: p.isConnected(),
      models: p.listModels(),
    }));
  });

  ipcMain.handle("connectProvider", async (_e, _providerId: string, _credentials: unknown) => {
    // M5.4 will implement provider connect using secrets store
    return;
  });

  ipcMain.handle("disconnectProvider", async (_e, providerId: string) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.registry.unregister(providerId as any);
  });

  ipcMain.handle("setAgentModel", async (_e, agentId: string, providerId: string, modelId: string) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.registry.assignAgentModel(agentId as any, providerId as any, modelId);
  });

  // Chat
  ipcMain.handle("getChatHistory", async (_e, agentId: string, limit: number) => {
    const ctx = deps.getEngineContext();
    if (!ctx) return [];
    return ctx.db
      .prepare("SELECT * FROM chat_messages WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?")
      .all(agentId, limit);
  });

  ipcMain.handle("sendMessage", async (_e, agentId: string, content: string) => {
    // M5.9 will implement streaming chat via riskMgrRunner / runner
    return null;
  });

  ipcMain.handle("clearChatHistory", async (_e, agentId: string) => {
    const ctx = deps.getEngineContext();
    if (!ctx) throw new Error("engine not running");
    ctx.db.prepare("DELETE FROM chat_messages WHERE agent_id = ?").run(agentId);
  });

  // Engine control
  ipcMain.handle("pauseTrading", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return;
    ctx.collector.stop();
  });

  ipcMain.handle("resumeTrading", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return;
    await ctx.collector.start();
  });

  ipcMain.handle("emergencyStop", async () => {
    const ctx = deps.getEngineContext();
    if (!ctx) return;
    ctx.collector.stop();
    // M5.10 will also force-close all positions
  });
}
```

- [ ] **Step 3: Run + commit**

```bash
pnpm --filter @pmt/main test:run tests/ipc.test.ts
git add packages/main/src/ipc.ts packages/main/tests/ipc.test.ts
git commit -m "feat(main): add IPC handler skeleton with all 21 methods registered"
```

### Task M5.2: Wire `registerIpcHandlers` into app entry

**Files:**
- Modify: `packages/main/src/index.ts`

- [ ] **Step 1: In `onReady()`, after schedulers are created, add:**

```typescript
import { registerIpcHandlers } from "./ipc.js";

// Inside onReady, after coordinatorScheduler.start():
registerIpcHandlers({
  getEngineContext,
  getRiskMgrRunner: () => riskMgrRunner,
});
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/index.ts
git commit -m "feat(main): wire IPC handlers in app entry"
```

### Task M5.3: Real preload.ts with typed API

**Files:**
- Modify: `packages/main/src/preload.ts`

- [ ] **Step 1: Replace contents**

```typescript
import { contextBridge, ipcRenderer } from "electron";

const api = {
  // Portfolio
  getPortfolioState: () => ipcRenderer.invoke("getPortfolioState"),
  getOpenPositions: () => ipcRenderer.invoke("getOpenPositions"),
  getRecentClosedTrades: (limit: number) => ipcRenderer.invoke("getRecentClosedTrades", limit),

  // Coordinator
  getLatestCoordinatorBrief: () => ipcRenderer.invoke("getLatestCoordinatorBrief"),
  triggerCoordinatorNow: () => ipcRenderer.invoke("triggerCoordinatorNow"),

  // Reports
  getRecentReports: (limit: number) => ipcRenderer.invoke("getRecentReports", limit),
  getReportContent: (reportPath: string) => ipcRenderer.invoke("getReportContent", reportPath),
  triggerReviewerNow: () => ipcRenderer.invoke("triggerReviewerNow"),

  // Proposals
  getPendingProposals: () => ipcRenderer.invoke("getPendingProposals"),
  approveProposal: (id: number) => ipcRenderer.invoke("approveProposal", id),
  rejectProposal: (id: number) => ipcRenderer.invoke("rejectProposal", id),

  // Config
  getConfig: () => ipcRenderer.invoke("getConfig"),
  updateConfigField: (key: string, value: unknown) =>
    ipcRenderer.invoke("updateConfigField", key, value),

  // Providers
  listProviders: () => ipcRenderer.invoke("listProviders"),
  connectProvider: (providerId: string, credentials: unknown) =>
    ipcRenderer.invoke("connectProvider", providerId, credentials),
  disconnectProvider: (providerId: string) => ipcRenderer.invoke("disconnectProvider", providerId),
  setAgentModel: (agentId: string, providerId: string, modelId: string) =>
    ipcRenderer.invoke("setAgentModel", agentId, providerId, modelId),

  // Chat
  getChatHistory: (agentId: string, limit: number) =>
    ipcRenderer.invoke("getChatHistory", agentId, limit),
  sendMessage: (agentId: string, content: string) =>
    ipcRenderer.invoke("sendMessage", agentId, content),
  clearChatHistory: (agentId: string) => ipcRenderer.invoke("clearChatHistory", agentId),

  // Engine control
  pauseTrading: () => ipcRenderer.invoke("pauseTrading"),
  resumeTrading: () => ipcRenderer.invoke("resumeTrading"),
  emergencyStop: () => ipcRenderer.invoke("emergencyStop"),

  // Event subscriptions (Main → Renderer push)
  on: (event: string, handler: (...args: unknown[]) => void) => {
    const wrapped = (_e: unknown, ...args: unknown[]) => handler(...args);
    ipcRenderer.on(event, wrapped);
    return () => ipcRenderer.removeListener(event, wrapped);
  },
};

contextBridge.exposeInMainWorld("pmt", api);

// Type augmentation for the renderer side
export type PmtApi = typeof api;
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/preload.ts
git commit -m "feat(main): expose typed IPC API via preload contextBridge"
```

### Task M5.4: Provider connect implementation

**Files:**
- Modify: `packages/main/src/ipc.ts` — update the `connectProvider` handler

- [ ] **Step 1: Replace `connectProvider` body with**

```typescript
ipcMain.handle("connectProvider", async (_e, providerId: string, credentials: { apiKey?: string; baseUrl?: string }) => {
  const ctx = deps.getEngineContext();
  if (!ctx) throw new Error("engine not running");

  // Lazy import inside handler to avoid loading all SDKs at boot
  const { createOpenAICompatProvider, createAnthropicProvider, createGeminiProvider, createOllamaProvider, createBedrockProvider } = await import("@pmt/llm");
  const { createSecretStore } = await import("./secrets.js");
  const secrets = createSecretStore();

  let provider;
  switch (providerId) {
    case "anthropic_api":
      if (!credentials.apiKey) throw new Error("API key required");
      await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
      provider = createAnthropicProvider({ mode: "api_key", apiKey: credentials.apiKey });
      break;
    case "deepseek":
      if (!credentials.apiKey) throw new Error("API key required");
      await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
      provider = createOpenAICompatProvider({
        providerId: "deepseek" as any,
        displayName: "DeepSeek",
        apiKey: credentials.apiKey,
        baseUrl: "https://api.deepseek.com/v1",
        defaultModels: [
          { id: "deepseek-chat", contextWindow: 128000 },
          { id: "deepseek-reasoner", contextWindow: 128000 },
        ],
      });
      break;
    case "zhipu":
      if (!credentials.apiKey) throw new Error("API key required");
      await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
      provider = createOpenAICompatProvider({
        providerId: "zhipu" as any,
        displayName: "Zhipu / Z.ai",
        apiKey: credentials.apiKey,
        baseUrl: "https://open.bigmodel.cn/api/paas/v4",
        defaultModels: [
          { id: "glm-4.5", contextWindow: 128000 },
          { id: "glm-4-flash", contextWindow: 128000 },
        ],
      });
      break;
    case "openai":
      if (!credentials.apiKey) throw new Error("API key required");
      await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
      provider = createOpenAICompatProvider({
        providerId: "openai" as any,
        displayName: "OpenAI",
        apiKey: credentials.apiKey,
        baseUrl: "https://api.openai.com/v1",
        defaultModels: [{ id: "gpt-5", contextWindow: 200000 }],
      });
      break;
    case "gemini_api":
      if (!credentials.apiKey) throw new Error("API key required");
      await secrets.set(`provider_${providerId}_apiKey`, credentials.apiKey);
      provider = createGeminiProvider({ mode: "api_key", apiKey: credentials.apiKey });
      break;
    case "ollama":
      provider = createOllamaProvider({ baseUrl: credentials.baseUrl ?? "http://localhost:11434" });
      break;
    default:
      throw new Error(`unknown provider: ${providerId}`);
  }

  await provider.connect();
  ctx.registry.register(provider);
});
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/ipc.ts
git commit -m "feat(main): implement connectProvider IPC handler with secret storage"
```

### Task M5.5: Provider auto-load on boot

When the app starts, look up all stored credentials and reconnect each provider.

**Files:**
- Modify: `packages/main/src/lifecycle.ts`

- [ ] **Step 1: Add `loadStoredProviders()` after engine context creation in `bootEngine()`**

```typescript
// After creating registry but before returning context:
try {
  await loadStoredProviders(registry);
} catch (err) {
  console.error("[lifecycle] failed to load stored providers:", err);
}
```

And add this function at the bottom of `lifecycle.ts`:

```typescript
async function loadStoredProviders(registry: ProviderRegistry): Promise<void> {
  const { createSecretStore } = await import("./secrets.js");
  const { createAnthropicProvider, createOpenAICompatProvider, createGeminiProvider, createOllamaProvider } = await import("@pmt/llm");

  const secrets = createSecretStore();
  const keys = await secrets.listKeys();

  for (const key of keys) {
    if (!key.startsWith("provider_") || !key.endsWith("_apiKey")) continue;
    const providerId = key.slice("provider_".length, -("_apiKey".length));
    const apiKey = await secrets.get(key);
    if (!apiKey) continue;

    try {
      let provider;
      switch (providerId) {
        case "anthropic_api":
          provider = createAnthropicProvider({ mode: "api_key", apiKey });
          break;
        case "deepseek":
          provider = createOpenAICompatProvider({
            providerId: "deepseek" as any,
            displayName: "DeepSeek",
            apiKey,
            baseUrl: "https://api.deepseek.com/v1",
            defaultModels: [{ id: "deepseek-chat", contextWindow: 128000 }],
          });
          break;
        case "zhipu":
          provider = createOpenAICompatProvider({
            providerId: "zhipu" as any,
            displayName: "Zhipu",
            apiKey,
            baseUrl: "https://open.bigmodel.cn/api/paas/v4",
            defaultModels: [{ id: "glm-4.5", contextWindow: 128000 }],
          });
          break;
        case "openai":
          provider = createOpenAICompatProvider({
            providerId: "openai" as any,
            displayName: "OpenAI",
            apiKey,
            baseUrl: "https://api.openai.com/v1",
            defaultModels: [{ id: "gpt-5", contextWindow: 200000 }],
          });
          break;
        case "gemini_api":
          provider = createGeminiProvider({ mode: "api_key", apiKey });
          break;
      }
      if (provider) {
        await provider.connect();
        registry.register(provider);
      }
    } catch (err) {
      console.error(`[lifecycle] failed to reconnect ${providerId}:`, err);
    }
  }
}
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/lifecycle.ts
git commit -m "feat(main): auto-load stored providers on engine boot"
```

### Task M5.6: Wire scheduler trigger handlers

**Files:**
- Modify: `packages/main/src/index.ts` — pass schedulers into `registerIpcHandlers`
- Modify: `packages/main/src/ipc.ts` — accept scheduler refs and call them

- [ ] **Step 1: Update `IpcDeps` and trigger handlers in `ipc.ts`**

```typescript
// Add to IpcDeps:
import type { ReviewerScheduler } from "./reviewer-scheduler.js";
import type { CoordinatorScheduler } from "./coordinator.js";

export interface IpcDeps {
  getEngineContext: () => EngineContext | null;
  getRiskMgrRunner: () => RiskMgrRunner | null;
  getReviewerScheduler: () => ReviewerScheduler | null;
  getCoordinatorScheduler: () => CoordinatorScheduler | null;
}

// Replace triggerReviewerNow handler:
ipcMain.handle("triggerReviewerNow", async () => {
  const sched = deps.getReviewerScheduler();
  if (!sched) throw new Error("reviewer scheduler not started");
  await sched.triggerNow();
  return true;
});

// Replace triggerCoordinatorNow handler:
ipcMain.handle("triggerCoordinatorNow", async () => {
  const sched = deps.getCoordinatorScheduler();
  if (!sched) throw new Error("coordinator scheduler not started");
  return sched.triggerNow();
});
```

- [ ] **Step 2: Update `index.ts` to pass schedulers**

```typescript
registerIpcHandlers({
  getEngineContext,
  getRiskMgrRunner: () => riskMgrRunner,
  getReviewerScheduler: () => reviewerScheduler,
  getCoordinatorScheduler: () => coordinatorScheduler,
});
```

- [ ] **Step 3: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/ipc.ts packages/main/src/index.ts
git commit -m "feat(main): wire reviewer and coordinator scheduler trigger handlers"
```

### Task M5.7: Reports listing from filesystem

**Files:**
- Modify: `packages/main/src/ipc.ts` — implement `getRecentReports` and `getReportContent`

- [ ] **Step 1: Replace handlers**

```typescript
ipcMain.handle("getRecentReports", async (_e, limit: number) => {
  const { readdirSync, statSync, readFileSync } = await import("node:fs");
  const { join } = await import("node:path");
  const { homedir } = await import("node:os");
  const reportsDir = process.env.POLYMARKET_TRADER_HOME
    ? join(process.env.POLYMARKET_TRADER_HOME, "reports")
    : join(homedir(), ".polymarket-trader", "reports");

  try {
    const files = readdirSync(reportsDir)
      .filter((f) => f.startsWith("review-") && f.endsWith(".md"))
      .map((f) => {
        const fullPath = join(reportsDir, f);
        const stat = statSync(fullPath);
        const dateStr = f.slice("review-".length, -".md".length);
        return {
          path: fullPath,
          date: dateStr,
          mtime: stat.mtimeMs,
        };
      })
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, limit);
    return files;
  } catch {
    return [];
  }
});

ipcMain.handle("getReportContent", async (_e, reportPath: string) => {
  const { readFileSync } = await import("node:fs");
  try {
    return readFileSync(reportPath, "utf-8");
  } catch {
    return "";
  }
});
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/ipc.ts
git commit -m "feat(main): implement getRecentReports and getReportContent handlers"
```

### Task M5.8: Approve proposal applies the change

**Files:**
- Modify: `packages/main/src/ipc.ts` — `approveProposal` actually writes to filter_config

- [ ] **Step 1: Replace handler**

```typescript
ipcMain.handle("approveProposal", async (_e, id: number) => {
  const ctx = deps.getEngineContext();
  if (!ctx) throw new Error("engine not running");
  const proposal = ctx.db
    .prepare("SELECT * FROM filter_proposals WHERE proposal_id = ?")
    .get(id) as { field: string; proposed_value: string; status: string } | undefined;
  if (!proposal) throw new Error(`proposal ${id} not found`);
  if (proposal.status !== "pending") throw new Error(`proposal ${id} is not pending`);

  // Apply to filter_config
  ctx.db.transaction(() => {
    ctx.db
      .prepare("INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source")
      .run(proposal.field, proposal.proposed_value, Date.now(), `proposal:${id}`);
    ctx.db
      .prepare("UPDATE filter_proposals SET status = 'approved', reviewed_at = ? WHERE proposal_id = ?")
      .run(Date.now(), id);
  })();
});
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/ipc.ts
git commit -m "feat(main): approveProposal applies change to filter_config"
```

### Task M5.9: Streaming chat IPC

**Files:**
- Modify: `packages/main/src/ipc.ts` — implement `sendMessage` with streaming via webContents.send
- Modify: `packages/main/src/index.ts` — pass `mainWindow.webContents()` into IpcDeps

- [ ] **Step 1: Update IpcDeps and sendMessage handler**

```typescript
import type { WindowHandle } from "./window.js";

export interface IpcDeps {
  getEngineContext: () => EngineContext | null;
  getRiskMgrRunner: () => RiskMgrRunner | null;
  getReviewerScheduler: () => ReviewerScheduler | null;
  getCoordinatorScheduler: () => CoordinatorScheduler | null;
  getMainWindow: () => WindowHandle | null;
}

// Replace sendMessage handler:
ipcMain.handle("sendMessage", async (_e, agentId: string, content: string) => {
  const ctx = deps.getEngineContext();
  const window = deps.getMainWindow();
  if (!ctx) throw new Error("engine not running");

  // Persist user message
  ctx.db
    .prepare(
      "INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)"
    )
    .run(agentId, "user", content, Date.now());

  if (agentId !== "risk_manager") {
    // M5: only risk_manager has reactive chat. Analyzer/Reviewer chats can be added later.
    const placeholder = `(${agentId} chat not yet wired — coming in a follow-up task)`;
    ctx.db
      .prepare("INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)")
      .run(agentId, "assistant", placeholder, Date.now());
    return { content: placeholder };
  }

  const runner = deps.getRiskMgrRunner();
  if (!runner) throw new Error("risk manager runner not configured");

  // Build current system state
  const portfolioRows = ctx.db
    .prepare("SELECT key, value FROM portfolio_state")
    .all() as Array<{ key: string; value: string }>;
  const portfolioState = Object.fromEntries(portfolioRows.map((r) => [r.key, JSON.parse(r.value)]));
  const recentTrades = ctx.db
    .prepare(
      "SELECT market_title, direction, pnl_net_usdc, exit_reason FROM signal_log WHERE exit_at IS NOT NULL ORDER BY exit_at DESC LIMIT 5"
    )
    .all() as Array<{
    market_title: string;
    direction: string;
    pnl_net_usdc: number | null;
    exit_reason: string | null;
  }>;
  const openCount = (ctx.db
    .prepare("SELECT COUNT(*) as n FROM signal_log WHERE exit_at IS NULL")
    .get() as { n: number }).n;

  const reply = await runner.answerQuestion({
    question: content,
    systemState: {
      portfolioState: {
        current_equity: portfolioState.current_equity ?? 10000,
        day_start_equity: portfolioState.day_start_equity ?? 10000,
        daily_halt_triggered: portfolioState.daily_halt_triggered ?? false,
      },
      recentTrades,
      openPositionCount: openCount,
    },
  });

  // Persist assistant message
  ctx.db
    .prepare("INSERT INTO chat_messages (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)")
    .run(agentId, "assistant", reply, Date.now());

  // Notify renderer (event push)
  const wc = window?.webContents();
  wc?.send("chat:complete", { agentId, role: "assistant", content: reply });

  return { content: reply };
});
```

- [ ] **Step 2: Update `index.ts` to pass `getMainWindow`**

```typescript
registerIpcHandlers({
  getEngineContext,
  getRiskMgrRunner: () => riskMgrRunner,
  getReviewerScheduler: () => reviewerScheduler,
  getCoordinatorScheduler: () => coordinatorScheduler,
  getMainWindow: () => mainWindow,
});
```

- [ ] **Step 3: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/ipc.ts packages/main/src/index.ts
git commit -m "feat(main): implement sendMessage IPC for risk_manager reactive chat"
```

### Task M5.10: Renderer ipc-client typed wrapper

**Files:**
- Create: `packages/renderer/src/ipc-client.ts`

- [ ] **Step 1: Implement**

```typescript
// Typed wrapper around window.pmt exposed by preload.ts.
// Renderer code imports from this module instead of touching window.* directly.

export interface PortfolioState {
  total_capital: number;
  current_equity: number;
  day_start_equity: number;
  week_start_equity: number;
  peak_equity: number;
  current_drawdown: number;
  daily_halt_triggered: boolean;
  weekly_halt_triggered: boolean;
}

export interface OpenPosition {
  signal_id: string;
  market_id: string;
  market_title: string;
  direction: "buy_yes" | "buy_no";
  entry_price: number;
  size_usdc: number;
  triggered_at: number;
}

export interface ProviderInfo {
  providerId: string;
  displayName: string;
  authType: "api_key" | "oauth" | "cli_credential" | "aws";
  isConnected: boolean;
  models: Array<{ id: string; contextWindow: number }>;
}

export interface FilterProposalRow {
  proposal_id: number;
  field: string;
  old_value: string;
  proposed_value: string;
  rationale: string;
  sample_count: number;
  expected_delta_winrate: number | null;
  status: "pending" | "approved" | "rejected";
}

export interface CoordinatorLogRow {
  log_id: number;
  generated_at: number;
  summary: string;
  alerts: string;       // JSON string
  suggestions: string;  // JSON string
}

declare global {
  interface Window {
    pmt: {
      getPortfolioState(): Promise<PortfolioState | null>;
      getOpenPositions(): Promise<OpenPosition[]>;
      getRecentClosedTrades(limit: number): Promise<any[]>;
      getLatestCoordinatorBrief(): Promise<CoordinatorLogRow | null>;
      triggerCoordinatorNow(): Promise<unknown>;
      getRecentReports(limit: number): Promise<Array<{ path: string; date: string; mtime: number }>>;
      getReportContent(path: string): Promise<string>;
      triggerReviewerNow(): Promise<unknown>;
      getPendingProposals(): Promise<FilterProposalRow[]>;
      approveProposal(id: number): Promise<void>;
      rejectProposal(id: number): Promise<void>;
      getConfig(): Promise<unknown>;
      updateConfigField(key: string, value: unknown): Promise<void>;
      listProviders(): Promise<ProviderInfo[]>;
      connectProvider(providerId: string, credentials: unknown): Promise<void>;
      disconnectProvider(providerId: string): Promise<void>;
      setAgentModel(agentId: string, providerId: string, modelId: string): Promise<void>;
      getChatHistory(agentId: string, limit: number): Promise<any[]>;
      sendMessage(agentId: string, content: string): Promise<{ content: string }>;
      clearChatHistory(agentId: string): Promise<void>;
      pauseTrading(): Promise<void>;
      resumeTrading(): Promise<void>;
      emergencyStop(): Promise<void>;
      on(event: string, handler: (...args: unknown[]) => void): () => void;
    };
  }
}

export const pmt = (typeof window !== "undefined" ? window.pmt : undefined) as Window["pmt"];

export function isElectron(): boolean {
  return typeof window !== "undefined" && Boolean(window.pmt);
}
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/ipc-client.ts
git commit -m "feat(renderer): add typed IPC client wrapper"
```

### Task M5.11: Replace mock portfolio store with real IPC

**Files:**
- Modify: `packages/renderer/src/stores/portfolio.ts`

- [ ] **Step 1: Replace contents**

```typescript
import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

export interface PortfolioState {
  equity: number;
  todayPnl: number;
  weeklyWinRate: number;
  weeklyWins: number;
  weeklyTotal: number;
  drawdownPct: number;
  peakEquity: number;
  openPositionCount: number;
  maxOpenPositions: number;
  totalExposure: number;
  loaded: boolean;
  refresh: () => Promise<void>;
}

export const usePortfolio = create<PortfolioState>((set) => ({
  equity: 0,
  todayPnl: 0,
  weeklyWinRate: 0,
  weeklyWins: 0,
  weeklyTotal: 0,
  drawdownPct: 0,
  peakEquity: 0,
  openPositionCount: 0,
  maxOpenPositions: 8,
  totalExposure: 0,
  loaded: false,

  refresh: async () => {
    if (!isElectron()) return;
    const state = await pmt.getPortfolioState();
    if (!state) return;
    const positions = await pmt.getOpenPositions();
    const closedSinceWeekStart = await pmt.getRecentClosedTrades(100);
    const wins = closedSinceWeekStart.filter((t: any) => (t.pnl_net_usdc ?? 0) > 0).length;
    const totalExposure = positions.reduce((sum: number, p: any) => sum + (p.size_usdc ?? 0), 0);
    const drawdownPct = state.peak_equity > 0
      ? -((state.peak_equity - state.current_equity) / state.peak_equity) * 100
      : 0;
    set({
      equity: state.current_equity,
      todayPnl: state.current_equity - state.day_start_equity,
      weeklyWinRate: closedSinceWeekStart.length > 0 ? wins / closedSinceWeekStart.length : 0,
      weeklyWins: wins,
      weeklyTotal: closedSinceWeekStart.length,
      drawdownPct,
      peakEquity: state.peak_equity,
      openPositionCount: positions.length,
      maxOpenPositions: 8,
      totalExposure,
      loaded: true,
    });
  },
}));
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/stores/portfolio.ts
git commit -m "feat(renderer): wire portfolio store to real IPC"
```

### Task M5.12: Replace mock positions store

**Files:**
- Modify: `packages/renderer/src/stores/positions.ts`

- [ ] **Step 1: Replace contents**

```typescript
import { create } from "zustand";
import type { Position } from "../components/PositionTable.js";
import { pmt, isElectron } from "../ipc-client.js";

interface PositionsState {
  positions: Position[];
  loaded: boolean;
  refresh: () => Promise<void>;
}

function formatHeldDuration(triggeredAt: number): string {
  const ms = Date.now() - triggeredAt;
  const totalMin = Math.floor(ms / 60_000);
  if (totalMin < 60) return `${totalMin}m`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `${h}h ${m.toString().padStart(2, "0")}m`;
}

export const usePositions = create<PositionsState>((set) => ({
  positions: [],
  loaded: false,
  refresh: async () => {
    if (!isElectron()) return;
    const rows = await pmt.getOpenPositions();
    const positions: Position[] = rows.map((r: any) => ({
      signalId: r.signal_id,
      marketTitle: r.market_title,
      side: r.direction,
      entryPrice: r.entry_price,
      currentPrice: r.entry_price, // M6+ will track current_mid_price separately
      sizeUsdc: r.size_usdc,
      pnl: 0, // M6+ will compute live PnL
      heldDuration: formatHeldDuration(r.triggered_at),
    }));
    set({ positions, loaded: true });
  },
}));
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/stores/positions.ts
git commit -m "feat(renderer): wire positions store to real IPC"
```

### Task M5.13: Replace mock coordinator + chat stores; add useEffect refreshes in pages

**Files:**
- Modify: `packages/renderer/src/stores/coordinator.ts`
- Modify: `packages/renderer/src/stores/chat.ts`
- Modify: `packages/renderer/src/pages/Dashboard.tsx`
- Modify: `packages/renderer/src/pages/Chat.tsx`

- [ ] **Step 1: Coordinator store**

```typescript
import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

interface CoordinatorState {
  latestSummary: string;
  generatedMinutesAgo: number;
  refresh: () => Promise<void>;
}

export const useCoordinator = create<CoordinatorState>((set) => ({
  latestSummary: "(no brief yet)",
  generatedMinutesAgo: 0,
  refresh: async () => {
    if (!isElectron()) return;
    const brief = await pmt.getLatestCoordinatorBrief();
    if (!brief) return;
    set({
      latestSummary: brief.summary,
      generatedMinutesAgo: Math.floor((Date.now() - brief.generated_at) / 60_000),
    });
  },
}));
```

- [ ] **Step 2: Chat store**

```typescript
import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

export type AgentId = "analyzer" | "reviewer" | "risk_manager";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
}

interface ChatState {
  activeAgent: AgentId;
  setActiveAgent: (agent: AgentId) => void;
  messagesByAgent: Record<AgentId, ChatMessage[]>;
  loadHistory: (agent: AgentId) => Promise<void>;
  sendMessage: (agent: AgentId, content: string) => Promise<void>;
}

let nextLocalId = 1;

export const useChat = create<ChatState>((set, get) => ({
  activeAgent: "risk_manager",
  setActiveAgent: (agent) => {
    set({ activeAgent: agent });
    get().loadHistory(agent);
  },
  messagesByAgent: { analyzer: [], reviewer: [], risk_manager: [] },

  loadHistory: async (agent) => {
    if (!isElectron()) return;
    const rows = await pmt.getChatHistory(agent, 50);
    const messages: ChatMessage[] = rows
      .map((r: any) => ({
        id: r.message_id,
        role: r.role,
        content: r.content,
        timestamp: r.created_at,
      }))
      .reverse(); // DB returns DESC, we display ASC
    set((state) => ({
      messagesByAgent: { ...state.messagesByAgent, [agent]: messages },
    }));
  },

  sendMessage: async (agent, content) => {
    // Optimistically append user message
    const userMsg: ChatMessage = {
      id: -nextLocalId++,
      role: "user",
      content,
      timestamp: Date.now(),
    };
    set((state) => ({
      messagesByAgent: {
        ...state.messagesByAgent,
        [agent]: [...state.messagesByAgent[agent], userMsg],
      },
    }));

    if (!isElectron()) return;
    try {
      const reply = await pmt.sendMessage(agent, content);
      const assistantMsg: ChatMessage = {
        id: -nextLocalId++,
        role: "assistant",
        content: reply.content,
        timestamp: Date.now(),
      };
      set((state) => ({
        messagesByAgent: {
          ...state.messagesByAgent,
          [agent]: [...state.messagesByAgent[agent], assistantMsg],
        },
      }));
    } catch (err) {
      const errMsg: ChatMessage = {
        id: -nextLocalId++,
        role: "assistant",
        content: `(Error: ${String(err)})`,
        timestamp: Date.now(),
      };
      set((state) => ({
        messagesByAgent: {
          ...state.messagesByAgent,
          [agent]: [...state.messagesByAgent[agent], errMsg],
        },
      }));
    }
  },
}));
```

- [ ] **Step 3: Add useEffect refreshes in Dashboard.tsx**

Add at the top of the `Dashboard` function body, before the JSX return:

```typescript
import React, { useEffect } from "react";
// ...

export function Dashboard() {
  const portfolio = usePortfolio();
  const positions = usePositions();
  const coordinator = useCoordinator();

  useEffect(() => {
    portfolio.refresh();
    positions.refresh();
    coordinator.refresh();
    const interval = setInterval(() => {
      portfolio.refresh();
      positions.refresh();
      coordinator.refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // ... rest of return JSX (use positions.positions instead of destructured)
}
```

Update Chat.tsx similarly to call `loadHistory(activeAgent)` on mount and replace the mock setTimeout reply with `useChat.getState().sendMessage(activeAgent, text)`.

- [ ] **Step 4: Build, commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/stores/coordinator.ts packages/renderer/src/stores/chat.ts packages/renderer/src/pages/Dashboard.tsx packages/renderer/src/pages/Chat.tsx
git commit -m "feat(renderer): wire coordinator and chat stores to real IPC, add live refresh"
```

### Task M5.14: Settings page wired to real provider list and proposals

**Files:**
- Modify: `packages/renderer/src/stores/settings.ts`
- Modify: `packages/renderer/src/pages/Settings.tsx`

- [ ] **Step 1: Update settings store with real refresh**

Replace the mock data with:

```typescript
import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

// ... (interfaces stay the same)

export const useSettings = create<SettingsState>((set) => ({
  providers: [],
  agentModels: { analyzer: { providerId: "", modelId: "" }, reviewer: { providerId: "", modelId: "" }, risk_manager: { providerId: "", modelId: "" } },
  thresholds: { /* loaded from getConfig */ } as any,
  riskLimits: {} as any,
  pendingProposals: [],

  refresh: async () => {
    if (!isElectron()) return;
    const [providers, proposals, config] = await Promise.all([
      pmt.listProviders(),
      pmt.getPendingProposals(),
      pmt.getConfig(),
    ]);
    set({
      providers: providers.map((p) => ({
        id: p.providerId,
        name: p.displayName,
        authType: p.authType,
        isConnected: p.isConnected,
      })),
      pendingProposals: proposals.map((p) => ({
        id: p.proposal_id,
        field: p.field,
        oldValue: p.old_value,
        proposedValue: p.proposed_value,
        rationale: p.rationale,
        sampleCount: p.sample_count,
        expectedDeltaWinrate: p.expected_delta_winrate ?? 0,
      })),
      // thresholds + riskLimits parsed from config
    });
  },
}));
```

- [ ] **Step 2: Update Settings.tsx to call refresh on mount and approveProposal/rejectProposal via IPC**

```typescript
import { useEffect } from "react";
// ...
useEffect(() => {
  useSettings.getState().refresh?.();
}, []);

// In the proposal cards:
onApprove={async () => {
  await pmt.approveProposal(p.id);
  useSettings.getState().refresh?.();
}}
onReject={async () => {
  await pmt.rejectProposal(p.id);
  useSettings.getState().refresh?.();
}}
```

- [ ] **Step 3: Build, commit**

```bash
pnpm --filter @pmt/renderer build
git add packages/renderer/src/stores/settings.ts packages/renderer/src/pages/Settings.tsx
git commit -m "feat(renderer): wire Settings page to real provider list and proposals"
```

### Task M5.15: M5 manual verification gate

- [ ] **Step 1: Run full app**

```bash
cd D:/work/polymarket-trader
pnpm build
cd packages/main
NODE_ENV=development npx electron dist/index.js
```

(In another terminal: `pnpm --filter @pmt/renderer dev` for Vite hot reload.)

- [ ] **Step 2: Verify each feature**

- [ ] Open Settings, click "+ Add API key" on Anthropic, paste a real API key, verify it connects
- [ ] Restart app, verify the provider is auto-loaded (auto-load on boot)
- [ ] Open Chat → Risk Manager, ask "what's our drawdown right now?", verify a real LLM reply arrives
- [ ] Open Dashboard, verify position/PnL data refreshes every 5 seconds
- [ ] Click "Run Reviewer Now" button, verify a new report is generated
- [ ] Open Reports page, click the new report, verify content displays
- [ ] In Settings, approve a pending proposal, verify it disappears from the list and the threshold updates

- [ ] **Step 3: Fix anything broken**

```bash
git add -A
git commit -m "fix(m5): verification gate fixes (describe what)"
```

---

## M5 Verification Gate

- [ ] All 15 M5 tasks complete
- [ ] App boots, all 4 pages show real data
- [ ] Risk Manager chat actually calls LLM and returns real responses
- [ ] Settings modifications persist across app restarts
- [ ] No mock data left in any store

---

## M6 — Coordinator Auto-Apply + Notifications (~12 tasks)

Goal: filter_proposals high-confidence auto-apply works end-to-end. Coordinator's hourly brief triggers OS desktop notifications for critical alerts. Audit log of auto-applied changes.

### Task M6.1: Auto-apply hook in Reviewer flow

**Files:**
- Modify: `packages/main/src/auto-apply.ts` — add `processProposals()` function
- Modify: `packages/main/src/index.ts` — call after each Reviewer run
- Create: `packages/main/tests/auto-apply-process.test.ts`

- [ ] **Step 1: Test**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { runMigrations } from "@pmt/engine/db";
import { processProposals } from "../src/auto-apply.js";

describe("processProposals", () => {
  let db: Database.Database;

  beforeEach(() => {
    db = new Database(":memory:");
    runMigrations(db);
  });

  it("auto-applies a high-confidence proposal", () => {
    db.prepare(
      "INSERT INTO filter_proposals (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(Date.now(), "min_net_flow_1m", "3000", "3500", "test", 50, 0.08);

    const result = processProposals(db);
    expect(result.applied).toBe(1);
    expect(result.skipped).toBe(0);

    const config = db
      .prepare("SELECT value FROM filter_config WHERE key = ?")
      .get("min_net_flow_1m") as { value: string } | undefined;
    expect(config?.value).toBe("3500");

    const proposal = db
      .prepare("SELECT status FROM filter_proposals WHERE field = ?")
      .get("min_net_flow_1m") as { status: string };
    expect(proposal.status).toBe("approved");
  });

  it("skips low-confidence proposal (small sample)", () => {
    db.prepare(
      "INSERT INTO filter_proposals (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(Date.now(), "min_net_flow_1m", "3000", "3500", "test", 10, 0.10);

    const result = processProposals(db);
    expect(result.applied).toBe(0);
    expect(result.skipped).toBe(1);

    const proposal = db
      .prepare("SELECT status FROM filter_proposals WHERE field = ?")
      .get("min_net_flow_1m") as { status: string };
    expect(proposal.status).toBe("pending"); // unchanged
  });

  it("skips locked field even with high confidence", () => {
    db.prepare(
      "INSERT INTO filter_proposals (created_at, field, old_value, proposed_value, rationale, sample_count, expected_delta_winrate) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(Date.now(), "static_dead_zone_min", "0.60", "0.55", "test", 100, 0.20);

    const result = processProposals(db);
    expect(result.applied).toBe(0);
    expect(result.skipped).toBe(1);
  });
});
```

- [ ] **Step 2: Add `processProposals` to `packages/main/src/auto-apply.ts`**

```typescript
import type Database from "better-sqlite3";

// (existing evaluateAutoApply function stays as-is)

export interface ProcessProposalsResult {
  applied: number;
  skipped: number;
}

export function processProposals(db: Database.Database): ProcessProposalsResult {
  const pending = db
    .prepare(
      "SELECT proposal_id, field, proposed_value, sample_count, expected_delta_winrate FROM filter_proposals WHERE status = 'pending'"
    )
    .all() as Array<{
    proposal_id: number;
    field: string;
    proposed_value: string;
    sample_count: number;
    expected_delta_winrate: number | null;
  }>;

  let applied = 0;
  let skipped = 0;

  for (const p of pending) {
    const decision = evaluateAutoApply({
      sample_count: p.sample_count,
      expected_delta_winrate: p.expected_delta_winrate,
      field: p.field,
      proposed_value: p.proposed_value,
    });

    if (decision.shouldApply) {
      db.transaction(() => {
        db.prepare(
          "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
        ).run(p.field, p.proposed_value, Date.now(), `auto-apply:${p.proposal_id}`);
        db.prepare(
          "UPDATE filter_proposals SET status = 'approved', reviewed_at = ? WHERE proposal_id = ?"
        ).run(Date.now(), p.proposal_id);
      })();
      applied++;
    } else {
      skipped++;
    }
  }

  return { applied, skipped };
}
```

- [ ] **Step 3: Wire into index.ts after each Reviewer run**

In `reviewerScheduler`'s `runReviewer` callback in `index.ts`, after the Reviewer completes:

```typescript
runReviewer: async () => {
  const result = await runReviewer({ /* ...existing args... */ });
  // After Reviewer generates new proposals, immediately try to auto-apply
  const ctx = getEngineContext();
  if (ctx) {
    const autoApplyResult = processProposals(ctx.db);
    console.log("[reviewer] auto-apply:", autoApplyResult);
  }
  return result;
},
```

- [ ] **Step 4: Build + commit**

```bash
pnpm --filter @pmt/main test:run tests/auto-apply-process.test.ts
pnpm --filter @pmt/main build
git add packages/main/src/auto-apply.ts packages/main/src/index.ts packages/main/tests/auto-apply-process.test.ts
git commit -m "feat(main): auto-apply high-confidence proposals after Reviewer runs"
```

### Task M6.2: Coordinator alerts → desktop notifications

**Files:**
- Modify: `packages/main/src/index.ts` — in `coordinatorScheduler`'s `onBrief`, show notifications for critical alerts

- [ ] **Step 1: Update onBrief callback**

```typescript
onBrief: (brief) => {
  // Persist to coordinator_log
  ctx.db.prepare(
    "INSERT INTO coordinator_log (generated_at, summary, alerts, suggestions, context_snapshot, model_used) VALUES (?, ?, ?, ?, ?, ?)"
  ).run(
    Date.now(),
    brief.summary,
    JSON.stringify(brief.alerts),
    JSON.stringify(brief.suggestions),
    "{}",
    ""
  );

  // Show OS notification for any critical alerts
  for (const alert of brief.alerts) {
    if (alert.severity === "critical") {
      showNotification({
        title: "Polymarket Trader: Critical Alert",
        body: alert.text,
      });
    } else if (alert.severity === "warning") {
      showNotification({
        title: "Polymarket Trader: Warning",
        body: alert.text,
        silent: true,
      });
    }
  }

  // Push event to renderer (Dashboard banner update)
  const wc = mainWindow?.webContents();
  wc?.send("coordinator:brief", brief);
},
```

- [ ] **Step 2: Build, commit**

```bash
pnpm --filter @pmt/main build
git add packages/main/src/index.ts
git commit -m "feat(main): show desktop notifications for critical Coordinator alerts"
```

### Task M6.3: Renderer subscribes to coordinator:brief event

**Files:**
- Modify: `packages/renderer/src/stores/coordinator.ts`

- [ ] **Step 1: Add event subscription on store creation**

```typescript
import { create } from "zustand";
import { pmt, isElectron } from "../ipc-client.js";

interface CoordinatorState {
  latestSummary: string;
  generatedMinutesAgo: number;
  refresh: () => Promise<void>;
}

export const useCoordinator = create<CoordinatorState>((set) => {
  // Subscribe to push events
  if (isElectron()) {
    pmt.on("coordinator:brief", (brief: any) => {
      set({
        latestSummary: brief.summary,
        generatedMinutesAgo: 0,
      });
    });
  }

  return {
    latestSummary: "(no brief yet)",
    generatedMinutesAgo: 0,
    refresh: async () => {
      if (!isElectron()) return;
      const brief = await pmt.getLatestCoordinatorBrief();
      if (!brief) return;
      set({
        latestSummary: brief.summary,
        generatedMinutesAgo: Math.floor((Date.now() - brief.generated_at) / 60_000),
      });
    },
  };
});
```

- [ ] **Step 2: Commit**

```bash
git add packages/renderer/src/stores/coordinator.ts
git commit -m "feat(renderer): subscribe to coordinator:brief push events"
```

### Task M6.4: Audit log table for auto-apply rollback

**Files:**
- Modify: `packages/engine/src/db/schema.sql` — add filter_config_history table
- Modify: `packages/engine/src/db/migrations.ts` — bump CURRENT_VERSION to 3

- [ ] **Step 1: Append to schema.sql**

```sql
-- filter_config_history: audit log for auto-applied changes (M6 added)
CREATE TABLE IF NOT EXISTS filter_config_history (
  history_id INTEGER PRIMARY KEY AUTOINCREMENT,
  field TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT NOT NULL,
  source TEXT NOT NULL,                                 -- 'auto-apply:<id>' / 'user' / 'proposal:<id>'
  applied_at INTEGER NOT NULL,
  rolled_back_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_filter_config_history_field ON filter_config_history(field, applied_at DESC);
```

- [ ] **Step 2: Bump migration version**

```typescript
const CURRENT_VERSION = 3;
```

- [ ] **Step 3: Update `processProposals` in `auto-apply.ts` to write audit row**

In the transaction inside `processProposals`, before the INSERT into filter_config:

```typescript
// Write audit row
const oldRow = db.prepare("SELECT value FROM filter_config WHERE key = ?").get(p.field) as { value: string } | undefined;
db.prepare(
  "INSERT INTO filter_config_history (field, old_value, new_value, source, applied_at) VALUES (?, ?, ?, ?, ?)"
).run(p.field, oldRow?.value ?? null, p.proposed_value, `auto-apply:${p.proposal_id}`, Date.now());
```

- [ ] **Step 4: Build + tests + commit**

```bash
pnpm --filter @pmt/engine test:run
pnpm --filter @pmt/main test:run
pnpm build
git add packages/engine/src/db/schema.sql packages/engine/src/db/migrations.ts packages/main/src/auto-apply.ts
git commit -m "feat: add filter_config_history audit log for auto-apply"
```

### Task M6.5: Rollback IPC + UI button

**Files:**
- Modify: `packages/main/src/ipc.ts` — add `rollbackProposal` handler
- Modify: `packages/main/src/preload.ts` — expose `rollbackProposal`
- Modify: `packages/renderer/src/ipc-client.ts` — add type
- Modify: `packages/renderer/src/pages/Reports.tsx` — show audit-applied changes with Rollback button

- [ ] **Step 1: Add rollback handler in ipc.ts**

```typescript
ipcMain.handle("rollbackAutoApply", async (_e, historyId: number) => {
  const ctx = deps.getEngineContext();
  if (!ctx) throw new Error("engine not running");

  const row = ctx.db
    .prepare("SELECT * FROM filter_config_history WHERE history_id = ? AND rolled_back_at IS NULL")
    .get(historyId) as { field: string; old_value: string | null; applied_at: number } | undefined;
  if (!row) throw new Error(`history ${historyId} not found or already rolled back`);

  // Only allow rollback within 24h
  if (Date.now() - row.applied_at > 24 * 60 * 60 * 1000) {
    throw new Error("rollback window expired (>24h)");
  }

  ctx.db.transaction(() => {
    if (row.old_value === null) {
      ctx.db.prepare("DELETE FROM filter_config WHERE key = ?").run(row.field);
    } else {
      ctx.db.prepare(
        "INSERT INTO filter_config (key, value, updated_at, source) VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, source=excluded.source"
      ).run(row.field, row.old_value, Date.now(), `rollback:${historyId}`);
    }
    ctx.db.prepare("UPDATE filter_config_history SET rolled_back_at = ? WHERE history_id = ?").run(Date.now(), historyId);
  })();
});
```

- [ ] **Step 2: Expose in preload + ipc-client + UI** — same pattern as other handlers, add rollback button to Reports page where auto-applied changes are listed.

- [ ] **Step 3: Build, commit**

```bash
pnpm --filter @pmt/main build
pnpm --filter @pmt/renderer build
git add packages/main/src/ipc.ts packages/main/src/preload.ts packages/renderer/src/ipc-client.ts packages/renderer/src/pages/Reports.tsx
git commit -m "feat: add rollback for auto-applied filter_config changes"
```

### Tasks M6.6 - M6.12: Auto-apply audit log UI, Coordinator history view, configurable Coordinator interval, etc.

Each is a small task following the patterns from M5 and M6.1-M6.5. Bundled here as a single bullet list for brevity:

- [ ] **M6.6**: Add a "Coordinator History" tab/section in Reports page showing the last 24 briefs from `coordinator_log` table
- [ ] **M6.7**: Add `coordinator_interval_min` to config + Settings UI slider (15min / 30min / 1h / 4h / 6h options)
- [ ] **M6.8**: Add a "View change history" button in Settings → Trading Thresholds that opens a modal showing `filter_config_history` rows
- [ ] **M6.9**: Add `engine:halted` and `engine:resumed` event push from main → renderer when circuit breakers fire
- [ ] **M6.10**: Renderer toast notification component that listens to `engine:halted`/`engine:resumed`
- [ ] **M6.11**: Tray icon updates: change icon color when halted (red icon overlay)
- [ ] **M6.12**: Add "Pause Trading" / "Resume Trading" / "Emergency Stop" buttons to Dashboard wired to existing IPC

Each task: TDD where applicable, commit per task. Since the patterns repeat, no full code listings here.

---

## M6 Verification Gate

- [ ] Reviewer runs → high-confidence proposals auto-apply → audit row written
- [ ] Critical Coordinator alerts → OS desktop notification
- [ ] User can rollback an auto-applied change within 24h
- [ ] Engine halt/resume events visible in tray + UI toast
- [ ] All tests pass, build clean

---

## M7 — Packaging + Stability Observation (~10 tasks)

Goal: produce installable `.exe` / `.dmg` / `.AppImage` files via electron-builder. Document install instructions. Then run 2-4 weeks of paper trading observation.

### Task M7.1: electron-builder config

**Files:**
- Create: `electron-builder.config.json`
- Modify: root `package.json` — add `dist:electron` script

- [ ] **Step 1: `electron-builder.config.json`**

```json
{
  "appId": "com.polymarket-trader.desktop",
  "productName": "Polymarket Trader",
  "directories": {
    "output": "dist-electron",
    "buildResources": "build-resources"
  },
  "files": [
    "packages/main/dist/**/*",
    "packages/llm/dist/**/*",
    "packages/engine/dist/**/*",
    "packages/renderer/dist/**/*",
    "package.json"
  ],
  "extraMetadata": {
    "main": "packages/main/dist/index.js"
  },
  "asar": true,
  "win": {
    "target": "nsis",
    "icon": "build-resources/icon.ico"
  },
  "mac": {
    "target": ["dmg", "zip"],
    "icon": "build-resources/icon.icns",
    "category": "public.app-category.finance"
  },
  "linux": {
    "target": ["AppImage", "deb"],
    "icon": "build-resources/icon.png",
    "category": "Office"
  },
  "nsis": {
    "oneClick": false,
    "perMachine": false,
    "allowToChangeInstallationDirectory": true
  }
}
```

- [ ] **Step 2: Add `dist:electron` script to root `package.json`**

```json
"scripts": {
  "build": "pnpm -r build",
  "test": "pnpm -r test",
  "test:run": "pnpm -r test:run",
  "typecheck": "pnpm -r typecheck",
  "clean": "pnpm -r clean",
  "dist:electron": "pnpm build && electron-builder --config electron-builder.config.json"
}
```

- [ ] **Step 3: Add electron-builder devDep at root**

```bash
cd D:/work/polymarket-trader
pnpm add -D -w electron-builder
```

- [ ] **Step 4: Commit**

```bash
git add electron-builder.config.json package.json pnpm-lock.yaml
git commit -m "feat(packaging): add electron-builder config for Win/macOS/Linux"
```

### Task M7.2: Build resources (icons + entitlements)

**Files:**
- Create: `build-resources/icon.png` (1024×1024 placeholder)
- Create: `build-resources/icon.ico` (Windows multi-res)
- Create: `build-resources/icon.icns` (macOS multi-res)

- [ ] **Step 1: Generate placeholder icons**

For v1 use a simple purple square with "PMT" text. Tools:
- macOS: `iconutil` to convert .png → .icns
- Cross-platform: `electron-icon-builder` npm package

```bash
pnpm add -D -w electron-icon-builder
mkdir -p build-resources
# Create or place a 1024x1024 PNG at build-resources/icon-source.png
npx electron-icon-builder --input=build-resources/icon-source.png --output=build-resources --flatten
```

- [ ] **Step 2: Verify icons created**

```bash
ls build-resources/
# Should show: icon.png, icon.ico, icon.icns
```

- [ ] **Step 3: Commit**

```bash
git add build-resources/
git commit -m "chore(packaging): add app icons (placeholder)"
```

### Task M7.3: Package script + native rebuild integration

**Files:**
- Modify: root `package.json` — add postinstall hook for native rebuild

- [ ] **Step 1: Add postinstall script**

```json
"scripts": {
  "postinstall": "electron-builder install-app-deps",
  // ... others
}
```

This rebuilds better-sqlite3 against the Electron Node version automatically after `pnpm install`.

- [ ] **Step 2: Test on the dev machine**

```bash
pnpm install
pnpm dist:electron
```

Expected: `dist-electron/` contains a `.exe` (or `.dmg` / `.AppImage` depending on platform) of size ~90-100 MB.

- [ ] **Step 3: Commit**

```bash
git add package.json
git commit -m "feat(packaging): wire electron-builder native rebuild postinstall"
```

### Task M7.4: First-run welcome experience

**Files:**
- Create: `packages/renderer/src/components/WelcomeWizard.tsx`
- Modify: `packages/renderer/src/App.tsx` — show wizard on first launch

- [ ] **Step 1: Implement a 3-step wizard**

Step 1: "Welcome to Polymarket Trader" + brief intro
Step 2: Configure first LLM provider (route to Settings)
Step 3: "You're ready" + start button

- [ ] **Step 2: Detect first launch via app_state KV**

Check `app_state` for `welcome_completed = true`. If not present, show wizard. After completion, write the flag.

- [ ] **Step 3: Commit**

```bash
git add packages/renderer/src/components/WelcomeWizard.tsx packages/renderer/src/App.tsx
git commit -m "feat(renderer): add first-run welcome wizard"
```

### Task M7.5: README install instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace top of README with**

```markdown
# Polymarket Trader

A standalone desktop application for stable, continuous Polymarket prediction-market trading. Three LLM-powered agent employees (Analyzer / Reviewer / Risk Manager) automate signal judgment, daily review, and risk monitoring.

## Install

### Pre-built (recommended)

Download the latest release for your OS from [GitHub Releases](https://github.com/west-garden/polymarket-trader/releases):

- **Windows**: `Polymarket-Trader-Setup-X.Y.Z.exe`
- **macOS**: `Polymarket-Trader-X.Y.Z.dmg`
- **Linux**: `Polymarket-Trader-X.Y.Z.AppImage`

After install, launch the app and follow the welcome wizard to configure your first LLM provider.

### From source

```bash
git clone https://github.com/west-garden/polymarket-trader.git
cd polymarket-trader
pnpm install
pnpm build
cd packages/main
npx electron dist/index.js
```

## Configuration

Storage paths (no manual config needed):
- Database: `~/.polymarket-trader/data.db`
- Reports: `~/.polymarket-trader/reports/`
- API keys: OS keychain (encrypted via Electron `safeStorage`)

## Security note

The v1 release is **not code-signed**. Windows/macOS will show a "publisher unverified" warning on first launch:
- Windows: click "More info" → "Run anyway"
- macOS: System Settings → Privacy → "Open Anyway" for Polymarket Trader

## What it does

(brief overview of trading engine + 3 agents + safety mechanisms — see `docs/specs/2026-04-07-desktop-app-design.md` for full design)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add install instructions and security note to README"
```

### Task M7.6: Stability observation runbook

**Files:**
- Create: `docs/m4-runbook.md` (M4 in the engine plan was the same concept; this one extends it)

- [ ] **Step 1: Write runbook** — same structure as the engine M4 runbook (`packages/engine/docs/m4-runbook.md`), but adapted for desktop app:

```markdown
# Desktop App M7 Stability Runbook

## Pre-flight checklist

- [ ] Installed Polymarket Trader (built from M7.3 dist or installed from .exe)
- [ ] Configured at least 1 LLM provider (Anthropic API key, Subscription, or Gemini OAuth)
- [ ] Configured per-agent model assignment for all 3 agents
- [ ] Polymarket WS URL reachable
- [ ] Sufficient disk space for SQLite + reports

## Daily checks

- [ ] Open Dashboard, verify equity and PnL look sensible
- [ ] Check Reports for the previous day's review
- [ ] Look at Coordinator History for any warning/critical alerts
- [ ] Verify no unexpected halts in Settings → Risk Limits

## Weekly checks

- [ ] Review weekly Reviewer report
- [ ] Approve / reject pending filter proposals
- [ ] Compare per-bucket win rates vs prior weeks

## Exit criteria for M7 phase

Stability declared OK when over 2 weeks:
- [ ] No app crashes
- [ ] Daily halt fired ≤ 0 times (or only when a real loss series justifies it)
- [ ] Total drawdown < 5%
- [ ] At least 50 closed trades in signal_log
- [ ] At least 1 auto-applied proposal proven beneficial in next week

## Failure criteria (rollback or pause)

- App crashes ≥ 3 times in a week
- Total drawdown > 10%
- Zero triggers for 5+ consecutive days (config too strict)
```

- [ ] **Step 2: Commit**

```bash
git add docs/m4-runbook.md
git commit -m "docs: add desktop app stability observation runbook"
```

### Tasks M7.7 - M7.10: Misc packaging polish

- [ ] **M7.7**: Add `dist:electron-win` / `dist:electron-mac` / `dist:electron-linux` per-platform scripts
- [ ] **M7.8**: Test installer on at least one OS (Windows .exe install + first launch)
- [ ] **M7.9**: Add CI workflow stub (`.github/workflows/release.yml`) that runs `pnpm dist:electron` on tag push (not enabled yet — manual release for v1)
- [ ] **M7.10**: Tag v0.2.0 release and upload artifact to GitHub Releases

---

## M7 Verification Gate

- [ ] `pnpm dist:electron` produces a runnable installer for the host OS
- [ ] Installer launches the app and welcome wizard works
- [ ] App functions across restart (config persists, db survives)
- [ ] README install instructions verified by following them on a clean machine
- [ ] First v0.2.0 release tagged

---

## Spec Coverage Check

| Spec section | Tasks covering it |
|--------------|-------------------|
| §1.1 核心目标 | All M1-M7 (full plan implements the goals) |
| §1.3 非目标 | Confirmed by absence of those features in any task |
| §2 架构 | M1 (monorepo + packages) |
| §3.1 13-step pipeline | M1 (engine relocation) — pipeline already implemented in engine |
| §3.2 LLM 4-class scheduling | M2 (provider layer) + M3 (schedulers) + M5 (chat) |
| §3.3 自主进化 4 触发点 | M6 (auto-apply + audit log) |
| §3.4 Coordinator | M3.6 + M5.13 + M6.2 |
| §4 UI 4 pages + Kraken style | M4 (full UI) + M5 (real data wiring) |
| §4.3 24+ providers | M2.2-M2.5 (5 adapters covering 24 providers) + M5.4 (connect handlers) |
| §5.1 4 new tables | M1.7 (chat_messages, coordinator_log, llm_provider_state, app_state) + M6.4 (filter_config_history) |
| §5.4 IPC architecture | M5 (full IPC layer) |
| §5.6 Streaming chat | M5.9 (sendMessage handler — currently non-streaming, streaming deferred to a small follow-up) |
| §5.7 Security (contextIsolation, etc.) | M3.3 (window config) + M5.3 (preload contextBridge) |
| §6 Milestones | M1 = Foundation, M2 = LLM, M3 = Electron, M4 = UI mocked, M5 = IPC, M6 = Coordinator/auto-apply, M7 = Packaging |
| §7 Distribution | M7 (electron-builder) |
| §8 Risks | M1 I3 (better-sqlite3 rebuild), M2.3 (Anthropic CLI), M3.4 (rendererUrl path) |

**Gaps identified during self-review:**

1. **Streaming chat is implemented as non-streaming in M5.9** — the `sendMessage` handler awaits the full LLM response before returning. The renderer doesn't see token-by-token output. This violates spec §5.6. **Add follow-up Task M5.9b** that switches to `streamChat` and emits `chat:streaming` events. (Marked as defer in M5 since the UI works without it; user can prioritize this in a follow-up.)

2. **DESIGN.md hard reference** — spec §1.1.5 says "any future UI must base on a DESIGN.md from VoltAgent/awesome-design-md". M4.1 copies kraken DESIGN.md but doesn't enforce that future component additions reference it. This is a process/documentation gap, not a code one.

3. **Engine `packages/engine/src/index.ts` barrel export** assumes every subdirectory has an `index.ts` re-exporter. Verify each subdir created in M1.2 Step 5 has the file. If any are missing, the build will fail with module-not-found.

These are documented for the implementer to address as they arise.

---

## Final Notes

- **Total tasks: ~93** (some bundled in M6.6-M6.12 and M7.7-M7.10)
- **Per-package tests** continue to run via `pnpm test:run` workspace-wide
- **Each task = one commit** wherever feasible; bundled tasks may have 2-3 commits
- **Investigation tasks (I3, I4, I5)** must be completed before M1 begins
- **Manual smoke tests** at M3.11, M5.15, and M7.10 are unavoidable — Electron + LLM + UI cannot be fully tested in CI

When something feels unclear during implementation, refer back to:
- `docs/specs/2026-04-07-desktop-app-design.md` — overall design intent
- `docs/specs/2026-04-06-polymarket-trading-agents-design.md` — engine spec (how the trading logic works)
- `docs/plans/2026-04-06-polymarket-trader-plugin.md` — how the existing engine was built (160 tests, well-validated patterns)

