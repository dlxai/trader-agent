import { describe, it, expect } from "vitest";
import { createBedrockProvider } from "../../src/adapters/bedrock.js";

describe("bedrock adapter", () => {
  it("constructs with AWS credentials", () => {
    const provider = createBedrockProvider({
      region: "us-east-1",
      accessKeyId: "AKIA-test",
      secretAccessKey: "secret-test",
    });
    expect(provider.id).toBe("bedrock");
    expect(provider.authType).toBe("aws");
  });

  it("lists default Bedrock models", async () => {
    const provider = createBedrockProvider({
      region: "us-east-1",
      accessKeyId: "x",
      secretAccessKey: "y",
    });
    await provider.connect();
    expect(provider.listModels().map((m) => m.id)).toContain("anthropic.claude-opus-4-v1:0");
  });
});
