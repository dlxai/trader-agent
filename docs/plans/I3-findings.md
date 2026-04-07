# I3: better-sqlite3 + Electron native rebuild

**Date:** 2026-04-07
**Investigator:** subagent

## Current state

- better-sqlite3 version installed: 11.10.0
- Has prebuilt binaries: yes — `build/Release/better_sqlite3.node` (compiled for system Node at install time via `prebuild-install || node-gyp rebuild`)
- Currently used by: `src/db/` (connection, migrations, all 7 repos) and `src/reviewer/reviewer.ts` via direct require

## The 3 rebuild approaches considered

### (a) electron-rebuild

The original community tool. Rebuilds native bindings against the Electron Node.js headers.

- **Install:** `npm install --save-dev electron-rebuild` (or `pnpm add -D electron-rebuild`)
- **Usage:** `npx electron-rebuild -f -w better-sqlite3`
- **pnpm integration:** Does not integrate automatically. Must be run manually or wired into a `postinstall` script by hand.
- **Frequency:** Must be re-run every time Electron version changes or after `pnpm install` clears/rewrites node_modules. No automatic hook.
- **Status:** Largely superseded by `@electron/rebuild`. Still works but is not the recommended path for new projects.

### (b) @electron/rebuild

The officially maintained fork by the Electron team. Drop-in replacement for `electron-rebuild` with better version detection and active maintenance.

- **Install:** `pnpm add -D @electron/rebuild`
- **Usage:** `npx electron-rebuild -f -w better-sqlite3` (same CLI surface)
- **pnpm integration:** Same as (a) — no automatic hook out of the box. Can be added to `postinstall` manually.
- **Frequency:** Same as (a) — runs once per invocation; must be wired to `postinstall` manually.
- **Advantage over (a):** Actively maintained, follows Electron releases, better Windows MSVC support.

### (c) electron-builder install-app-deps

A subcommand of `electron-builder` (the standard Electron packaging tool) that rebuilds ALL native deps for the target Electron version automatically.

- **Install:** `pnpm add -D electron-builder` (needed for packaging anyway in M7)
- **Usage:** `electron-builder install-app-deps`
- **pnpm integration:** Yes — wire once in root `package.json` as `"postinstall": "electron-builder install-app-deps"`, then it runs automatically on every `pnpm install`.
- **Frequency:** Runs every `pnpm install` automatically (postinstall hook).
- **Advantage:** Rebuilds ALL native deps, not just better-sqlite3 — future-proof for anything added later.

## Chosen approach

**electron-builder install-app-deps** (option c)

**Rationale:**
- Already going to use electron-builder for packaging in M7 (per plan §6 / §7)
- Works as a postinstall hook — runs automatically after every `pnpm install`
- Handles native rebuild for ALL deps, not just better-sqlite3 (future-proof)
- Used by all major production Electron apps

## Required postinstall script

In root `package.json`:

```json
"scripts": {
  "postinstall": "electron-builder install-app-deps"
}
```

This needs `electron-builder` in devDependencies (added in M7.1).

**M1 implication**: M1 doesn't need to install electron-builder yet because the engine still works with the system Node version. The rebuild only matters once we actually launch Electron in M3. So either:
- (a) Add the postinstall and electron-builder to devDeps in M1.4 (when scaffolding @pmt/main)
- (b) Wait until M3 when we actually try to start Electron

**Recommendation: (a)** — front-load the install pain to M1 so M3 doesn't have a surprise breakage.

## Verification (how to confirm engine works inside Electron at runtime)

Once Electron is set up in M3:

```bash
cd packages/main
npx electron -e "const Database = require('better-sqlite3'); const db = new Database(':memory:'); console.log(db.prepare('SELECT 1 as ok').get());"
```

Expected output: `{ ok: 1 }`. If you get `NODE_MODULE_VERSION` mismatch, the rebuild didn't run.

## Risk

If rebuild fails on Windows: usually because Visual Studio Build Tools missing. Document in README that Windows users need `npm install --global windows-build-tools` (or use a prebuilt approach as fallback).

If rebuild fails on macOS: usually Xcode Command Line Tools missing. `xcode-select --install` fixes it.

If rebuild fails on Linux: usually `python3-dev` and `build-essential` missing. Standard build tools.

## Open issues / unknowns

- Pinning a specific Electron version is important so the rebuild stays cached. We use Electron `^30.0.0` per the plan; the rebuild output is keyed on the exact version.
- pnpm hoists dependencies differently than npm — `electron-builder install-app-deps` should still work but verify in M1.
