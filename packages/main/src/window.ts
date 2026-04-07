import { BrowserWindow, app } from "electron";

export interface WindowDeps {
  preloadPath: string;
  rendererUrl: string;
  /** dev mode: load from Vite dev server. prod mode: load from file:// */
  isDev: boolean;
}

export interface WindowHandle {
  show(): void;
  hide(): void;
  close(): void;
  isVisible(): boolean;
  webContents(): Electron.WebContents;
}

export function createMainWindow(deps: WindowDeps): WindowHandle {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false, // start hidden, tray controls visibility
    title: "Polymarket Trader",
    webPreferences: {
      preload: deps.preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (deps.isDev) {
    window.loadURL(deps.rendererUrl);
    window.webContents.openDevTools();
  } else {
    window.loadFile(deps.rendererUrl);
  }

  // Don't actually quit on close — hide to tray instead
  window.on("close", (e) => {
    if (!(app as unknown as Record<string, unknown>).isQuittingExplicit) {
      e.preventDefault();
      window.hide();
    }
  });

  return {
    show() {
      window.show();
      window.focus();
    },
    hide() {
      window.hide();
    },
    close() {
      (app as unknown as Record<string, unknown>).isQuittingExplicit = true;
      window.close();
    },
    isVisible() {
      return window.isVisible();
    },
    webContents() {
      return window.webContents;
    },
  };
}
