const ONE_DAY_MS = 24 * 60 * 60 * 1000;
const CHECK_INTERVAL_MS = 60 * 60 * 1000; // re-evaluate every hour

export interface ReviewerSchedulerDeps {
  runReviewer: () => Promise<{ bucketCount: number; killSwitches: number; reportPath: string }>;
  lastRunAt: () => number | null;
  onRun: () => void;
}

export interface ReviewerScheduler {
  start(): void;
  stop(): void;
  triggerNow(): Promise<void>;
}

export function createReviewerScheduler(deps: ReviewerSchedulerDeps): ReviewerScheduler {
  let timer: NodeJS.Timeout | null = null;

  async function maybeRun(): Promise<void> {
    const last = deps.lastRunAt();
    const now = Date.now();
    if (last === null || now - last >= ONE_DAY_MS) {
      try {
        await deps.runReviewer();
        deps.onRun();
      } catch (err) {
        console.error("[reviewer-scheduler] run failed:", err);
      }
    }
  }

  return {
    start() {
      // Schedule the first check for immediately
      timer = setTimeout(async () => {
        await maybeRun();
        // After the first run, schedule periodic checks
        timer = setInterval(() => {
          maybeRun().catch((err) => {
            console.error("[reviewer-scheduler] run failed:", err);
          });
        }, CHECK_INTERVAL_MS);
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
      await deps.runReviewer();
      deps.onRun();
    },
  };
}
