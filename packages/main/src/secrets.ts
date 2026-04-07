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
