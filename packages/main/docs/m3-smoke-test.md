# M3 Smoke Test — Electron app starts

## Prerequisites
- M1 + M2 + M3 tasks all complete
- All package tests pass: `pnpm test:run`

## Steps

### 1. Build all packages
```bash
cd D:/work/polymarket-trader
pnpm build
```

Expected: 4 dist directories (engine, llm, main, renderer), no errors.

### 2. Start Electron from main package
```bash
cd packages/main
npx electron dist/index.js
```

In dev mode you would set `NODE_ENV=development` and have the renderer Vite server running (`pnpm --filter @pmt/renderer dev` in another terminal), but for an M3 smoke test we just want to see the empty placeholder window backed by the M1.5 renderer scaffold.

### 3. Visual checks
- [ ] System tray icon appears
- [ ] Empty Electron window appears with title "Polymarket Trader"
- [ ] Closing the window hides it (does not quit) — tray icon stays
- [ ] Right-click tray → "Show Window" reopens it
- [ ] Right-click tray → "Quit" terminates the app

### 4. Engine running checks
While the app is open, in another terminal:
- [ ] `~/.polymarket-trader/data.db` (or the OS userData equivalent) file was created
- [ ] No errors in the terminal log
- [ ] DB file size > 0 — schema migrated

### 5. Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `Cannot find module 'better-sqlite3'` | Native binding not rebuilt for Electron | `pnpm postinstall` (runs `electron-builder install-app-deps` per I3) |
| Window stays blank forever | preload path wrong | Check `dist/preload.js` exists |
| Tray icon doesn't appear (Linux) | Some distros don't show empty icons | OK for M3 — real icon comes in M7 |
| `app is not defined` import error | ESM/CJS interop issue | Check `package.json` has `"type": "module"` |
| `Failed to resolve entry for package "@pmt/engine"` | Engine `dist/` stale or extension mismatch | Run `pnpm --filter @pmt/engine build` then retry |

## Verification gate

Smoke test passes when all checkboxes in section 3 + section 4 are green. Capture a screenshot of tray + window for the record (optional).
