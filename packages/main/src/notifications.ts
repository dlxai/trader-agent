import { Notification } from "electron";

export interface DesktopNotification {
  title: string;
  body: string;
  silent?: boolean;
}

export function showNotification(input: DesktopNotification): void {
  if (!Notification.isSupported()) return;
  new Notification({
    title: input.title,
    body: input.body,
    silent: input.silent ?? false,
  }).show();
}
