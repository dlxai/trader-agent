import { describe, it, expect } from "vitest";
import { parseVerdict } from "../../src/analyzer/verdict-parser.js";
import { VerdictParseError } from "../../src/util/errors.js";

describe("parseVerdict", () => {
  it("parses a clean JSON verdict", () => {
    const raw = JSON.stringify({
      verdict: "real_signal",
      direction: "buy_yes",
      confidence: 0.75,
      reasoning: "Strong flow with 4 unique traders",
    });
    const parsed = parseVerdict(raw);
    expect(parsed.verdict).toBe("real_signal");
    expect(parsed.direction).toBe("buy_yes");
    expect(parsed.confidence).toBe(0.75);
  });

  it("extracts JSON embedded in markdown fences", () => {
    const raw = "```json\n" + JSON.stringify({
      verdict: "noise",
      direction: "buy_yes",
      confidence: 0.2,
      reasoning: "looks like bots",
    }) + "\n```";
    const parsed = parseVerdict(raw);
    expect(parsed.verdict).toBe("noise");
  });

  it("throws on invalid verdict value", () => {
    const raw = JSON.stringify({
      verdict: "probably",
      direction: "buy_yes",
      confidence: 0.5,
      reasoning: "",
    });
    expect(() => parseVerdict(raw)).toThrow(VerdictParseError);
  });

  it("throws on confidence out of [0, 1]", () => {
    const raw = JSON.stringify({
      verdict: "real_signal",
      direction: "buy_yes",
      confidence: 1.5,
      reasoning: "",
    });
    expect(() => parseVerdict(raw)).toThrow(VerdictParseError);
  });

  it("throws on non-JSON input", () => {
    expect(() => parseVerdict("I think yes")).toThrow(VerdictParseError);
  });
});
