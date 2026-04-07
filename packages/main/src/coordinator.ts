import type { CoordinatorBrief } from "@pmt/llm";

export interface CoordinatorSchedulerDeps {
  intervalMs: number;
  generateBrief: () => Promise<CoordinatorBrief | null>;
  onBrief: (brief: CoordinatorBrief) => void;
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
      if (brief) deps.onBrief(brief);
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
