/**
 * Electron preload script.
 *
 * M3: empty placeholder. M5 will use contextBridge to expose typed IPC API.
 */
import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("pmt", {
  __placeholder: true,
});
