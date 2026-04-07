import { describe, it, expect } from "vitest";
import { priceBucket, priorWinRate } from "../../src/executor/price-bucket.js";

describe("priceBucket", () => {
  it("floors to nearest 0.05", () => {
    expect(priceBucket(0.53)).toBe(0.50);
    expect(priceBucket(0.55)).toBe(0.55);
    expect(priceBucket(0.549)).toBe(0.50);
    expect(priceBucket(0.01)).toBe(0.00);
    expect(priceBucket(0.99)).toBe(0.95);
  });

  it("is stable at exact bucket edges", () => {
    expect(priceBucket(0.60)).toBe(0.60);
    expect(priceBucket(0.85)).toBe(0.85);
  });

  it("throws RangeError for prices outside [0, 1]", () => {
    expect(() => priceBucket(-0.1)).toThrow(RangeError);
    expect(() => priceBucket(1.1)).toThrow(RangeError);
  });
});

describe("priorWinRate", () => {
  it("returns 0.34 for dead zone buckets [0.60, 0.85]", () => {
    expect(priorWinRate(0.60)).toBe(0.34);
    expect(priorWinRate(0.70)).toBe(0.34);
    expect(priorWinRate(0.80)).toBe(0.34);
  });

  it("returns 0.34 at 0.85 (inclusive upper bound)", () => {
    expect(priorWinRate(0.85)).toBe(0.34);
  });

  it("returns 0.50 neutral outside dead zone", () => {
    expect(priorWinRate(0.50)).toBe(0.50);
    expect(priorWinRate(0.30)).toBe(0.50);
    expect(priorWinRate(0.90)).toBe(0.50);
    expect(priorWinRate(0.05)).toBe(0.50);
  });
});
