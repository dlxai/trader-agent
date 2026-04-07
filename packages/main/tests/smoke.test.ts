import { describe, it, expect } from "vitest";
import { PACKAGE_NAME } from "../src/index.js";

describe("@pmt/main smoke", () => {
  it("package loads", () => {
    expect(PACKAGE_NAME).toBe("@pmt/main");
  });
});
