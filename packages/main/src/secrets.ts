import { safeStorage, app } from "electron";
import { readFileSync, writeFileSync, existsSync, mkdirSync, unlinkSync, readdirSync } from "node:fs";
import { join } from "node:path";

export interface SecretStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  listKeys(): Promise<string[]>;
}

// Check if encryption is available at module load time
const ENCRYPTION_AVAILABLE = safeStorage.isEncryptionAvailable();

function pathFor(key: string, secretsDir: string): string {
  if (!/^[A-Za-z0-9._-]+$/.test(key)) {
    throw new Error(`secretStore: invalid key '${key}' — only alphanumerics, dot, underscore, dash`);
  }
  return join(secretsDir, key + (ENCRYPTION_AVAILABLE ? ".bin" : ".txt"));
}

/**
 * Creates a secret store backed by Electron's safeStorage (platform keychain
 * on macOS/Windows, libsecret on Linux). Encrypted blobs are written to disk
 * as one file per key under app.getPath("userData") + "/secrets/".
 *
 * Falls back to plain text storage if OS encryption is not available.
 */
export function createSecretStore(): SecretStore {
  const userDataDir = app.getPath("userData");
  const secretsDir = join(userDataDir, "secrets");
  mkdirSync(secretsDir, { recursive: true });

  if (!ENCRYPTION_AVAILABLE) {
    console.warn("[secrets] OS encryption not available, using plain text storage");
  }

  return {
    async get(key) {
      const path = pathFor(key, secretsDir);
      if (!existsSync(path)) return null;
      if (!ENCRYPTION_AVAILABLE) {
        return readFileSync(path, "utf-8");
      }
      const blob = readFileSync(path);
      return safeStorage.decryptString(blob);
    },
    async set(key, value) {
      if (!value) return; // Skip empty values
      const path = pathFor(key, secretsDir);
      if (!ENCRYPTION_AVAILABLE) {
        writeFileSync(path, value, "utf-8");
        return;
      }
      const blob = safeStorage.encryptString(value);
      writeFileSync(path, blob);
    },
    async delete(key) {
      const path = pathFor(key, secretsDir);
      if (existsSync(path)) unlinkSync(path);
    },
    async listKeys() {
      if (!existsSync(secretsDir)) return [];
      return readdirSync(secretsDir)
        .filter((name) => name.endsWith(ENCRYPTION_AVAILABLE ? ".bin" : ".txt"))
        .map((name) => name.slice(0, ENCRYPTION_AVAILABLE ? -4 : -4));
    },
  };
}
