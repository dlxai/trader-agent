import type { CoordinatorBrief, CoordinatorAction } from "@pmt/llm";

export interface CoordinatorSchedulerDeps {
  intervalMs: number;
  generateBrief: () => Promise<CoordinatorBrief | null>;
  onBrief: (brief: CoordinatorBrief) => void;
  onAction?: (action: CoordinatorAction) => Promise<void>;
}

export interface CoordinatorScheduler {
  start(): void;
  stop(): void;
  triggerNow(): Promise<CoordinatorBrief | null>;
}

export function createCoordinatorScheduler(deps: CoordinatorSchedulerDeps): CoordinatorScheduler {
  let timer: NodeJS.Timeout | null = null;

  async function runOnce(): Promise<CoordinatorBrief | null> {
    try {
      const brief = await deps.generateBrief();
      if (brief) {
        deps.onBrief(brief);
        if (deps.onAction && brief.actions && brief.actions.length > 0) {
          for (const action of brief.actions) {
            try {
              await deps.onAction(action);
            } catch (err) {
              console.error(`[coordinator] action ${action.type} failed:`, err);
            }
          }
        }
      }
      return brief;
    } catch (err) {
      console.error("[coordinator] run failed:", err);
      return null;
    }
  }

  return {
    start() {
      // Schedule the first run for immediately
      timer = setTimeout(async () => {
        await runOnce();
        // After the first run, schedule periodic runs
        timer = setInterval(() => {
          runOnce().catch((err) => {
            console.error("[coordinator] run failed:", err);
          });
        }, deps.intervalMs);
      }, 0);
    },
    stop() {
      if (timer) {
        clearTimeout(timer);
        clearInterval(timer);
      }
      timer = null;
    },
    async triggerNow() {
      return runOnce();
    },
  };
}
