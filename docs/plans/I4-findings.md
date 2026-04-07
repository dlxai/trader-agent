# I4: Anthropic CLI credentials format

**Date:** 2026-04-07
**Investigator:** subagent
**Platform tested:** Windows (paths may differ on macOS/Linux)

## File location

- **Windows:** `%USERPROFILE%\.claude\.credentials.json` — i.e. `C:\Users\<username>\.claude\.credentials.json` (verified exists on this machine)
- **macOS:** `~/.claude/.credentials.json` (theoretical — same `~/.claude` home dir, not tested)
- **Linux:** `~/.claude/.credentials.json` (theoretical — not tested)

The file was last modified `2026-04-07 01:23:51` local time and is 471 bytes (single line JSON).

## Schema (sanitized)

```json
{
  "claudeAiOauth": {
    "accessToken": "<redacted>",
    "refreshToken": "<redacted>",
    "expiresAt": 1775575431067,
    "scopes": [
      "user:file_upload",
      "user:inference",
      "user:mcp_servers",
      "user:profile",
      "user:sessions:claude_code"
    ],
    "subscriptionType": "max",
    "rateLimitTier": "default_claude_max_20x"
  }
}
```

### Field notes

| Field | Type | Description |
|---|---|---|
| `claudeAiOauth` | object | Top-level namespace; only key in the file |
| `claudeAiOauth.accessToken` | string | OAuth Bearer token (`sk-ant-oat01-…` prefix) |
| `claudeAiOauth.refreshToken` | string | OAuth refresh token (`sk-ant-ort01-…` prefix) |
| `claudeAiOauth.expiresAt` | number | Unix epoch **milliseconds** (not seconds) |
| `claudeAiOauth.scopes` | string[] | OAuth scopes granted |
| `claudeAiOauth.subscriptionType` | string | `"max"` on Anthropic Max; likely `"pro"` on Pro |
| `claudeAiOauth.rateLimitTier` | string | Rate-limit bucket string |

## Fields needed by AnthropicAdapter

- `claudeAiOauth.accessToken` — used as `Authorization: Bearer <token>` on every API request
- `claudeAiOauth.expiresAt` — compare against `Date.now()` (both in ms) before each request
- `claudeAiOauth.refreshToken` — exchange for a fresh `accessToken` when expired

## Refresh logic

The credentials file contains **both** an `accessToken` and a `refreshToken`. The `expiresAt` is a millisecond epoch. This means:

1. The adapter can check expiry without calling any external process — pure file read + comparison.
2. If expired, the adapter must call the Anthropic token endpoint to exchange the `refreshToken` for a new `accessToken` (and presumably a new `refreshToken` + `expiresAt`).
3. The refresh endpoint is **not documented publicly** as of April 2026, but Claude CLI itself performs this refresh. Two options at implementation time:
   - **Option A (preferred):** Shell out to `claude` CLI — e.g. run `claude api-key` or a similar command that forces a refresh and prints the token. This delegates refresh logic to the CLI.
   - **Option B:** Reverse-engineer the token endpoint from Claude CLI's source or network traffic. The URL is likely `https://auth.anthropic.com/oauth/token` or similar. Requires `grant_type=refresh_token`.
   - **Option C (simplest fallback):** On expiry, throw a clear error telling the user to restart Claude Code / run `claude login`, rather than attempting a programmatic refresh.

## Recommended `readCliToken` implementation pseudocode

```typescript
import * as fs from "fs/promises";
import * as os from "os";
import * as path from "path";

const CREDENTIALS_PATH = path.join(os.homedir(), ".claude", ".credentials.json");

// Margin: refresh 60 s before actual expiry to avoid race conditions
const EXPIRY_MARGIN_MS = 60_000;

interface ClaudeCredentials {
  claudeAiOauth: {
    accessToken: string;
    refreshToken: string;
    expiresAt: number; // ms epoch
    scopes: string[];
    subscriptionType: string;
    rateLimitTier: string;
  };
}

async function readCliToken(): Promise<string> {
  // 1. Read file
  let raw: string;
  try {
    raw = await fs.readFile(CREDENTIALS_PATH, "utf8");
  } catch {
    throw new Error(
      "Anthropic CLI credentials not found. Run `claude login` or paste an API key in Settings."
    );
  }

  // 2. Parse JSON
  let creds: ClaudeCredentials;
  try {
    creds = JSON.parse(raw);
  } catch {
    throw new Error(
      "Anthropic CLI credentials file is malformed. Run `claude login` to reset it."
    );
  }

  const oauth = creds?.claudeAiOauth;
  if (!oauth?.accessToken) {
    throw new Error(
      "Anthropic CLI credentials missing accessToken. Run `claude login`."
    );
  }

  // 3. Check expiry
  const nowMs = Date.now();
  if (oauth.expiresAt - nowMs < EXPIRY_MARGIN_MS) {
    // Option A: delegate refresh to CLI (simplest, most future-proof)
    // This assumes `claude` is on PATH and can silently refresh the token file.
    try {
      const { execFile } = await import("child_process");
      const { promisify } = await import("util");
      await promisify(execFile)("claude", ["login", "--refresh"], {
        timeout: 10_000,
      });
      // Re-read the updated credentials file
      const refreshed = JSON.parse(
        await fs.readFile(CREDENTIALS_PATH, "utf8")
      ) as ClaudeCredentials;
      return refreshed.claudeAiOauth.accessToken;
    } catch {
      throw new Error(
        "Anthropic CLI token is expired and auto-refresh failed. Run `claude login` to re-authenticate."
      );
    }
  }

  // 4. Return valid token
  return oauth.accessToken;
}
```

> **Note on the CLI refresh command:** The exact sub-command that forces a token refresh is unknown as of April 2026. Alternatives to investigate: `claude auth refresh`, running `claude` with no args (may auto-refresh silently), or directly calling the OAuth token endpoint with the refresh token. See Open Issues below.

## Fallback behavior

If credentials file is missing OR can't be parsed OR refresh fails:
- Throw a clear error: `"Anthropic CLI credentials not found. Run \`claude login\` or paste an API key in Settings."`
- The adapter should propagate this through the `AgentInvoker` chain so the user sees it in chat (not a silent crash).
- The UI should offer a fallback path to the API-key input screen.

## Open issues / unknowns

1. **Refresh endpoint / CLI command** — The exact Anthropic OAuth token-refresh REST endpoint URL is not publicly documented. Need to inspect `claude` CLI source or network traffic to find it (likely `https://auth.anthropic.com/oauth/token` with `grant_type=refresh_token`). The CLI command that triggers a silent refresh also needs verification.
2. **Write-back after refresh** — If the adapter calls the refresh endpoint directly (Option B), it must write the updated `accessToken`, `refreshToken`, and `expiresAt` back to `.credentials.json` so the CLI stays in sync. Option A (shell out to CLI) avoids this since the CLI manages the file itself.
3. **macOS/Linux path** — Assumed to be `~/.claude/.credentials.json` (same hidden dir). Unverified on non-Windows.
4. **`subscriptionType` values** — Observed `"max"` on Anthropic Max. Need to confirm what value appears for Pro subscribers and whether the API behaves identically.
5. **Token prefix format** — `accessToken` starts with `sk-ant-oat01-` and `refreshToken` with `sk-ant-ort01-`. These prefixes may change across Claude CLI versions; the adapter should NOT hard-code prefix validation.
6. **File permissions** — On Linux/macOS the file should be mode `600`. The adapter may want to warn (not fail) if it detects world-readable permissions.
7. **Concurrent access** — If the user is running Claude CLI and the adapter simultaneously, writing back a refreshed token may race. A file lock or atomic write strategy is needed for Option B.
