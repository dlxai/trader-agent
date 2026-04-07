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
