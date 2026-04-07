import { describe, it, expect, vi } from "vitest";
import { createTray } from "../src/tray.js";

vi.mock("electron", () => {
  const MockTray = vi.fn(function () {
    this.setToolTip = vi.fn();
    this.setContextMenu = vi.fn();
    this.on = vi.fn();
    this.destroy = vi.fn();
  });

  return {
    Tray: MockTray,
    Menu: {
      buildFromTemplate: vi.fn().mockReturnValue({}),
    },
    nativeImage: {
      createFromPath: vi.fn().mockReturnValue({}),
      createEmpty: vi.fn().mockReturnValue({}),
    },
  };
});

describe("tray", () => {
  it("creates a tray with a default menu", () => {
    const onShowWindow = vi.fn();
    const onQuit = vi.fn();
    const tray = createTray({ iconPath: undefined, onShowWindow, onQuit });
    expect(tray).toBeDefined();
    expect(tray.destroy).toBeDefined();
  });
});
