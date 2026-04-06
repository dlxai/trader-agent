import { describe, it, expect, vi } from "vitest";
import { definePlugin } from "../src/plugin-sdk.js";

describe("definePlugin", () => {
  it("returns an object with id, name, activate, register", () => {
    const plugin = definePlugin({
      id: "test",
      name: "Test",
      setup: () => {},
    });
    expect(plugin.id).toBe("test");
    expect(plugin.name).toBe("Test");
    expect(typeof plugin.activate).toBe("function");
    expect(typeof plugin.register).toBe("function");
  });

  it("invokes setup() on activate", () => {
    const setup = vi.fn();
    const plugin = definePlugin({ id: "x", name: "X", setup });
    const fakeApi = {
      id: "x",
      logger: { info: vi.fn(), warn: vi.fn() },
      on: vi.fn(),
    };
    plugin.activate(fakeApi as any);
    expect(setup).toHaveBeenCalledWith(fakeApi);
  });

  it("aliases register() to activate() for channel-plugin compatibility", () => {
    const setup = vi.fn();
    const plugin = definePlugin({ id: "x", name: "X", setup });
    const fakeApi = {
      id: "x",
      logger: { info: vi.fn(), warn: vi.fn() },
      on: vi.fn(),
    };
    plugin.register(fakeApi as any);
    expect(setup).toHaveBeenCalledWith(fakeApi);
  });

  it("registers tools when provided", () => {
    const registerTool = vi.fn();
    const plugin = definePlugin({
      id: "x",
      name: "X",
      tools: [
        { name: "do_thing", description: "test", parameters: {} },
      ],
      setup: () => {},
    });
    const fakeApi = {
      id: "x",
      logger: { info: vi.fn(), warn: vi.fn() },
      on: vi.fn(),
      registerTool,
    };
    plugin.activate(fakeApi as any);
    expect(registerTool).toHaveBeenCalledTimes(1);
  });
});
