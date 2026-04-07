import { describe, it, expect } from "vitest";
import { PACKAGE_NAME } from "../src/index.js";

describe("@pmt/llm smoke", () => {
  it("package loads", () => {
    expect(PACKAGE_NAME).toBe("@pmt/llm");
  });
});
