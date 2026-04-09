import { BrowserWindow, app, screen } from "electron";

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
  // Center window on primary display
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
  const windowWidth = 1280;
  const windowHeight = 800;
  const x = Math.round((screenWidth - windowWidth) / 2);
  const y = Math.round((screenHeight - windowHeight) / 2);

  const window = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x,
    y,
    minWidth: 1024,
    minHeight: 700,
    show: true, // show immediately so user can see the app
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

  // Handle window close - destroy tray when window is actually closing
  window.on("close", () => {
    // Window is actually closing, clean up will happen in before-quit
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
