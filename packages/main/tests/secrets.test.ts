import { describe, it, expect, vi, beforeEach } from "vitest";
import { createSecretStore } from "../src/secrets.js";

// Mock electron's safeStorage and app
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
