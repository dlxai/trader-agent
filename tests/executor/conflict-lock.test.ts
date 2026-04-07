import { describe, it, expect } from "vitest";
import { createConflictLock } from "../../src/executor/conflict-lock.js";

describe("conflictLock", () => {
  it("acquires lock for unheld market", () => {
    const lock = createConflictLock();
    expect(lock.tryAcquire("m1")).toBe(true);
  });

  it("rejects second acquisition for same market", () => {
    const lock = createConflictLock();
    expect(lock.tryAcquire("m1")).toBe(true);
    expect(lock.tryAcquire("m1")).toBe(false);
  });

  it("allows acquisition after release", () => {
    const lock = createConflictLock();
    lock.tryAcquire("m1");
    lock.release("m1");
    expect(lock.tryAcquire("m1")).toBe(true);
  });

  it("isolates locks across markets", () => {
    const lock = createConflictLock();
    expect(lock.tryAcquire("m1")).toBe(true);
    expect(lock.tryAcquire("m2")).toBe(true);
  });
});
