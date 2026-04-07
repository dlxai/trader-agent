import { Tray, Menu, nativeImage, type MenuItemConstructorOptions } from "electron";

export interface TrayDeps {
  iconPath?: string | undefined;
  onShowWindow: () => void;
  onQuit: () => void;
}

export interface TrayHandle {
  destroy(): void;
  updateStatus(status: TrayStatus): void;
}

export type TrayStatus =
  | { kind: "running"; positionCount: number; equity: number }
  | { kind: "halted"; reason: string }
  | { kind: "error"; message: string };

export function createTray(deps: TrayDeps): TrayHandle {
  const icon = deps.iconPath
    ? nativeImage.createFromPath(deps.iconPath)
    : nativeImage.createEmpty();
  const tray = new Tray(icon);
  tray.setToolTip("Polymarket Trader");

  let currentStatus: TrayStatus = { kind: "running", positionCount: 0, equity: 0 };

  function buildMenu(): Menu {
    const statusLabel = formatStatusLabel(currentStatus);
    const items: MenuItemConstructorOptions[] = [
      { label: statusLabel, enabled: false },
      { type: "separator" },
      { label: "Show Window", click: deps.onShowWindow },
      { type: "separator" },
      { label: "Quit", click: deps.onQuit },
    ];
    return Menu.buildFromTemplate(items);
  }

  tray.setContextMenu(buildMenu());
  tray.on("double-click", deps.onShowWindow);

  return {
    destroy() {
      tray.destroy();
    },
    updateStatus(status) {
      currentStatus = status;
      tray.setContextMenu(buildMenu());
      tray.setToolTip(`Polymarket Trader — ${formatStatusLabel(status)}`);
    },
  };
}

function formatStatusLabel(status: TrayStatus): string {
  switch (status.kind) {
    case "running":
      return `Running · ${status.positionCount} positions · $${status.equity.toFixed(0)}`;
    case "halted":
      return `Halted: ${status.reason}`;
    case "error":
      return `Error: ${status.message.slice(0, 40)}`;
  }
}
