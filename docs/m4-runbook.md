# M4 Stability Observation Runbook

## Pre-flight checklist (complete before starting the observation window)

- [ ] Plugin loaded in OpenClaw (logs show "[polymarket] activated")
- [ ] OpenClaw running with isolated `OPENCLAW_HOME=~/.polymarket-trader/openclaw`
- [ ] Collector is publishing trigger events (check log for "[collector] trigger published")
- [ ] Analyzer agent is configured at `~/.polymarket-trader/openclaw/agents/polymarket-analyzer/`
- [ ] Reviewer agent is configured at `~/.polymarket-trader/openclaw/agents/polymarket-reviewer/`
- [ ] Cron entry for reviewer is in `~/.polymarket-trader/openclaw/cron/jobs.json`
- [ ] portfolio_state initialized with $10,000 virtual capital
- [ ] All unit + E2E tests pass

## Observation metrics (track daily)

Run this SQL against `$POLYMARKET_TRADER_HOME/data.db`:

```sql
-- Daily summary
SELECT
  date(triggered_at / 1000, 'unixepoch') AS day,
  count(*) AS trades,
  sum(CASE WHEN pnl_net_usdc > 0 THEN 1 ELSE 0 END) AS wins,
  round(sum(pnl_net_usdc), 2) AS daily_net_pnl,
  round(avg(pnl_net_usdc), 2) AS avg_per_trade
FROM signal_log
WHERE exit_at IS NOT NULL
GROUP BY day
ORDER BY day DESC;
```

## Exit criteria for M4

The M4 phase is successful when ALL of these hold over a 2-week window:

- [ ] No unexpected plugin crashes
- [ ] `signal_log` has at least 50 closed trades
- [ ] No day triggered the 2% daily halt
- [ ] Total drawdown from peak < 10%
- [ ] Reviewer has run successfully at least 5 times (cron)
- [ ] At least 1 `filter_proposals` row exists (Reviewer is generating suggestions)

## Failure criteria (abort M4 and re-plan)

Stop and revisit the spec if ANY of these happen:
- Total drawdown > 10% (emergency stop triggers)
- Plugin crashes > 3 times in a week
- Zero triggers for 3+ consecutive days (thresholds are too strict)
- > 20% of trades have identical entry/exit prices (paper fill bug)

## Post-M4 decisions to make

Based on M4 data, answer:
1. Are the default trigger thresholds producing a sensible number of signals per day? (target: 5-20/day)
2. Is the [0.60, 0.85] dead zone actually being respected? (`SELECT count(*) FROM signal_log WHERE price_bucket BETWEEN 0.60 AND 0.85` should be 0)
3. Is the Reviewer's per-bucket win rate calibration converging? (compare prior vs observed for buckets with >= 10 samples)
4. Should any kill switches from Reviewer be upheld or reverted?
5. Is the system ready for Phase 2 (adding Regime Gate, considering Live Executor)?
