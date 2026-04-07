# I5: Gemini OAuth in Electron

**Date:** 2026-04-07
**Investigator:** subagent

## The 3 approaches considered

### (a) Default browser + localhost callback (RECOMMENDED)

Electron opens the OAuth consent URL via `shell.openExternal`. The redirect URI points to `http://127.0.0.1:<port>/oauth-callback`. Electron spins up a tiny Node `http.Server` on that port just long enough to receive `?code=...`, then shuts down. The code is exchanged for tokens server-side (still local — the POST goes from the main process to Google's token endpoint).

**Pros:**
- User sees the consent screen in their real browser, where they are already logged in to Google — no re-authentication required.
- Most familiar UX; identical to how Google's own `gcloud auth login` works on the desktop.
- Works on all platforms (Windows / macOS / Linux) without special Electron permissions.
- Fully compatible with `safeStorage` — tokens never leave the main process.
- Supports PKCE, so no `client_secret` is strictly required for public clients.

**Cons:**
- Requires binding a localhost port. In theory a port collision is possible; mitigated by scanning for a free port before starting the server.
- The callback window (a bare browser tab) briefly flickers to a "you can close this tab" page after the redirect — minor cosmetic issue.

**Complexity:** Low. ~100 lines of Node: `http.createServer`, URL parsing, one `fetch` to the token endpoint.

**safeStorage:** Fully compatible. Tokens are handled entirely in the main process and written via `secrets.set(...)`.

---

### (b) BrowserWindow with redirect interception

Open a new `BrowserWindow` navigated to the Google OAuth URL. Listen for `webContents.on('will-redirect', ...)` (or `will-navigate`) to intercept the redirect back to the `redirect_uri`. Parse `code=` from the intercepted URL, then exchange it for tokens.

**Pros:**
- Self-contained — no HTTP server, no browser tab management.
- Easier to add a loading spinner or custom close button.

**Cons:**
- User must re-enter their Google credentials inside Electron's Chromium frame — cookies from their system browser are not shared. This is a significant UX regression.
- Google's OAuth consent page sometimes detects embedded WebViews and blocks the flow or shows an "unsupported browser" warning. Google explicitly discourages this pattern for desktop apps.
- Requires `partition` + session management to avoid storing Google cookies in the app profile.
- More moving parts (BrowserWindow lifecycle, session cleanup).

**Complexity:** Medium. More event wiring than option (a), but no HTTP server.

**safeStorage:** Compatible — tokens still handled in main process.

---

### (c) Device flow

Show a short user code (e.g. `ABCD-1234`) in the UI and a URL (`https://www.google.com/device`). User visits the URL on any device, types the code, approves. Electron polls `https://oauth2.googleapis.com/token` until the user completes the step.

**Pros:**
- Zero callback infrastructure — no port, no redirect URI.
- Works in fully headless environments or behind strict firewalls.

**Cons:**
- Worst UX by a wide margin: users must manually type a code. Normal consumer users find this confusing and abandon the flow.
- Google's device authorization endpoint requires explicit enablement in the Cloud Console project and is rate-limited more aggressively.
- The polling interval means a minimum delay of several seconds before the grant is recognized.

**Complexity:** Low-medium (polling loop, but no server or BrowserWindow).

**safeStorage:** Compatible.

---

## Chosen approach

**(a) Default browser + localhost callback**

**Rationale:** Best UX; standard pattern for desktop OAuth; Google's own examples (`gcloud`, Google Drive desktop) use this; straightforward Node implementation; works seamlessly with safeStorage.

---

## Implementation outline

```typescript
// packages/main/src/gemini-oauth.ts (sketch — implement in M2.4 or M5.4)

import { shell } from "electron";
import http from "node:http";
import { randomBytes, createHash } from "node:crypto";

const CLIENT_ID = "<our-pre-registered-desktop-client-id>";
// client_secret is required for "Desktop app" type in Google Cloud Console.
// It is NOT a user secret — Google's own docs acknowledge it ships in binaries.
const CLIENT_SECRET = "<our-pre-registered-secret>";
const SCOPE = "https://www.googleapis.com/auth/generative-language.retriever openid email";
const TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token";
const AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";

/** Pick an available localhost port by binding to :0 */
async function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = http.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as { port: number }).port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

/** Generate PKCE verifier + challenge */
function pkce(): { verifier: string; challenge: string } {
  const verifier = randomBytes(32).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}

export async function startGeminiOAuth(): Promise<{
  access_token: string;
  refresh_token: string;
  expires_at: number; // epoch ms
}> {
  const port = await findFreePort();
  const redirectUri = `http://127.0.0.1:${port}/oauth-callback`;
  const state = randomBytes(16).toString("hex");
  const { verifier, challenge } = pkce();

  // 1. Build consent URL
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: SCOPE,
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
    access_type: "offline",   // ensures refresh_token is returned
    prompt: "consent",        // force refresh_token even if already granted
  });
  const consentUrl = `${AUTH_ENDPOINT}?${params}`;

  // 2. Wait for callback
  const code = await new Promise<string>((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url!, `http://127.0.0.1:${port}`);
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end("<h1>Authorisation complete — you can close this tab.</h1>");
      server.close();

      const returnedState = url.searchParams.get("state");
      const code = url.searchParams.get("code");
      const error = url.searchParams.get("error");

      if (error) return reject(new Error(`OAuth error: ${error}`));
      if (returnedState !== state) return reject(new Error("State mismatch"));
      if (!code) return reject(new Error("No code in callback"));
      resolve(code);
    });

    server.listen(port, "127.0.0.1");
    // Time-out if user never completes the flow
    setTimeout(() => { server.close(); reject(new Error("OAuth timeout")); }, 5 * 60 * 1000);
  });

  // 3. Open browser (after server is listening)
  await shell.openExternal(consentUrl);

  // 4. Exchange code for tokens
  const body = new URLSearchParams({
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    code,
    code_verifier: verifier,
    grant_type: "authorization_code",
    redirect_uri: redirectUri,
  });
  const resp = await fetch(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!resp.ok) throw new Error(`Token exchange failed: ${await resp.text()}`);
  const json = await resp.json() as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  return {
    access_token: json.access_token,
    refresh_token: json.refresh_token,
    expires_at: Date.now() + json.expires_in * 1000,
  };
}
```

**Note on ordering:** `shell.openExternal` is called *after* the callback server is `listen`ing, so the server is guaranteed to be ready before the browser redirect arrives.

---

## Required dependencies

- Built-in Node `http` and `node:crypto` — no external packages needed.
- `shell` from Electron (already available in main process).
- Optional: `google-auth-library` npm package if we want automatic refresh with retry logic. For v1 a manual refresh call (~20 lines) is simpler and avoids adding a Google dependency.

---

## Google Cloud project setup

**Option 1 — Ship a pre-registered "Polymarket Trader" desktop client (recommended for v1)**

Steps we (the developers) perform once:

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → New project: "Polymarket Trader".
2. Enable **Generative Language API** (API & Services → Library → search "Generative Language").
3. Configure OAuth consent screen:
   - User type: **External**
   - App name: "Polymarket Trader"
   - Scopes: add `https://www.googleapis.com/auth/generative-language.retriever` (or the verified correct scope — see Open Issues).
   - Test users: add your own email; stay in **Testing** status to avoid Google review for now.
4. Credentials → Create Credentials → **OAuth client ID**:
   - Application type: **Desktop app**
   - Name: "Polymarket Trader Desktop"
5. Download the JSON. Extract `client_id` and `client_secret` and embed them in `gemini-oauth.ts`.

**Pros:** Zero setup for users — they just click "Connect Google Account" in Settings.

**Cons:**
- `client_id` (and technically `client_secret`) are visible to anyone who unpacks the Electron `.asar`. However Google's own docs acknowledge this is unavoidable for desktop apps and explicitly say the `client_secret` is "not secret" for the Desktop app type. The real protection is that tokens are per-user and stored in their OS keychain.
- All users share the same OAuth client's rate-limit quota. For a personal trading tool this is unlikely to be a problem.
- While consent screen is in "Testing" status, tokens expire after 7 days (refresh_token is revoked). Once published (even without formal Google review for non-sensitive scopes) tokens last indefinitely. **Action: publish the consent screen before shipping v1.**

**Option 2 — Per-user Google Cloud project**

The user creates their own Google Cloud project and pastes their own `client_id` + `client_secret` into Settings.

**Pros:** User owns their quotas; no shared client concerns.

**Cons:** 5–10 minute Google Cloud Console setup is significant friction. Most users will not do it.

**Recommendation:** Ship Option 1. Document the shared quota limitation. Upgrade to Option 2 (or a proper OAuth app with Google verification) if quota becomes an issue.

---

## Token storage

```typescript
// In the connectProvider IPC handler (M5.x), after startGeminiOAuth() resolves:
await secrets.set("provider_gemini_oauth_access_token", tokens.access_token);
await secrets.set("provider_gemini_oauth_refresh_token", tokens.refresh_token);
await secrets.set("provider_gemini_oauth_expires_at", String(tokens.expires_at));
```

The `GeminiAdapter` in oauth mode receives a `getAccessToken` callback:

```typescript
getAccessToken: async () => {
  const expiresAt = Number(await secrets.get("provider_gemini_oauth_expires_at"));
  if (Date.now() < expiresAt - 60_000) {
    return secrets.get("provider_gemini_oauth_access_token");
  }
  // Refresh path — see below
  const newTokens = await refreshGeminiToken(
    await secrets.get("provider_gemini_oauth_refresh_token")!
  );
  await secrets.set("provider_gemini_oauth_access_token", newTokens.access_token);
  await secrets.set("provider_gemini_oauth_expires_at", String(newTokens.expires_at));
  return newTokens.access_token;
}
```

This keeps all token handling in the main process; the renderer never sees raw tokens.

---

## Refresh logic

Google access tokens expire after **1 hour** (`expires_in: 3599`).

```typescript
async function refreshGeminiToken(refreshToken: string): Promise<{
  access_token: string;
  expires_at: number;
}> {
  const body = new URLSearchParams({
    client_id: CLIENT_ID,
    client_secret: CLIENT_SECRET,
    refresh_token: refreshToken,
    grant_type: "refresh_token",
  });
  const resp = await fetch(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!resp.ok) throw new Error(`Token refresh failed: ${await resp.text()}`);
  const json = await resp.json() as { access_token: string; expires_in: number };
  return {
    access_token: json.access_token,
    expires_at: Date.now() + json.expires_in * 1000,
  };
}
```

Note: A refresh response does **not** include a new `refresh_token` — keep using the original one indefinitely unless Google revokes it (consent screen "Testing" mode revokes after 7 days; "Published" mode does not).

---

## Open issues / unknowns

1. **Correct Gemini scope name** — The plan mentions `generative-language.retriever`. The actual scope for calling the Generative Language API (text generation, not just retrieval) may be `https://www.googleapis.com/auth/generative-language.api` or simply `https://www.googleapis.com/auth/cloud-platform`. **Action required before M2.4:** verify by checking the [Generative Language API auth docs](https://ai.google.dev/gemini-api/docs/oauth) or by creating a test Cloud project and inspecting what scope the API requires.

2. **Free tier availability on OAuth path** — The free Gemini tier (no billing account) is available on the API key path. Whether the same free quota applies to the OAuth path (using a Desktop app client) needs verification. It is plausible that OAuth calls are treated as "user-authenticated" requests to a paid project and therefore require billing enabled. **Action:** test with a fresh Cloud project (no billing) before advertising OAuth as the "free tier" option.

3. **OAuth consent screen review** — If we add any sensitive or restricted scopes, Google requires a formal review. `generative-language.retriever` / `generative-language.api` are not classified as sensitive as of early 2026, but this should be confirmed. Without review the app stays in Testing mode (7-day token expiry, max 100 test users).

4. **`client_secret` in binary** — Documented above as acceptable for Desktop app type per Google's own guidance. Worth a brief comment in the source file so future contributors don't flag it as a security issue.

5. **Windows Firewall prompt** — On Windows, binding a localhost TCP server may trigger a firewall dialog the first time. This is usually suppressed for loopback (`127.0.0.1`) but varies by Windows version and corporate policy. If it becomes an issue, the workaround is to use the BrowserWindow approach (option b) as a fallback on Windows only.
