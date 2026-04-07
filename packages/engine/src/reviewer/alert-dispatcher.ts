export type AlertSender = (channelId: string, userId: string, text: string) => Promise<boolean>;

export interface AlertDispatcherOptions {
  sender: AlertSender;
  channel: string | null;
  userId: string | null;
}

export interface Alert {
  severity: "info" | "warning" | "critical";
  title: string;
  body: string;
}

export interface AlertDispatcher {
  dispatch(alert: Alert): Promise<void>;
}

export function createAlertDispatcher(opts: AlertDispatcherOptions): AlertDispatcher {
  return {
    async dispatch(alert) {
      if (!opts.channel || !opts.userId) return;
      const text = `[${alert.severity.toUpperCase()}] ${alert.title}\n\n${alert.body}`;
      await opts.sender(opts.channel, opts.userId, text);
    },
  };
}
