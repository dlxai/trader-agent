-- signal_log: every triggered signal with entry + exit fields
CREATE TABLE IF NOT EXISTS signal_log (
  signal_id TEXT PRIMARY KEY,
  market_id TEXT NOT NULL,
  market_title TEXT NOT NULL,
  resolves_at INTEGER NOT NULL,
  triggered_at INTEGER NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy_yes', 'buy_no')),
  entry_price REAL NOT NULL,
  price_bucket REAL NOT NULL,
  size_usdc REAL NOT NULL,
  kelly_fraction REAL NOT NULL,
  snapshot_volume_1m REAL NOT NULL,
  snapshot_net_flow_1m REAL NOT NULL,
  snapshot_unique_traders_1m INTEGER NOT NULL,
  snapshot_price_move_5m REAL NOT NULL,
  snapshot_liquidity REAL NOT NULL,
  llm_verdict TEXT NOT NULL,
  llm_confidence REAL NOT NULL,
  llm_reasoning TEXT NOT NULL,
  exit_at INTEGER,
  exit_price REAL,
  exit_reason TEXT CHECK (exit_reason IN ('E', 'A_SL', 'A_TP', 'D', 'C') OR exit_reason IS NULL),
  pnl_gross_usdc REAL,
  fees_usdc REAL,
  slippage_usdc REAL,
  gas_usdc REAL,
  pnl_net_usdc REAL,
  holding_duration_sec INTEGER
);
CREATE INDEX IF NOT EXISTS idx_signal_log_market ON signal_log(market_id);
CREATE INDEX IF NOT EXISTS idx_signal_log_open ON signal_log(exit_at) WHERE exit_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_signal_log_bucket ON signal_log(price_bucket);

-- strategy_performance: per-bucket rolling stats (window = '7d' or '30d')
CREATE TABLE IF NOT EXISTS strategy_performance (
  price_bucket REAL NOT NULL,
  window TEXT NOT NULL CHECK (window IN ('7d', '30d')),
  trade_count INTEGER NOT NULL DEFAULT 0,
  win_count INTEGER NOT NULL DEFAULT 0,
  win_rate REAL NOT NULL DEFAULT 0.0,
  total_pnl_net_usdc REAL NOT NULL DEFAULT 0.0,
  last_updated INTEGER NOT NULL,
  PRIMARY KEY (price_bucket, window)
);

-- filter_config: KV hot-reloadable config
CREATE TABLE IF NOT EXISTS filter_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'default'
);

-- filter_proposals: Reviewer's pending suggestions
CREATE TABLE IF NOT EXISTS filter_proposals (
  proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at INTEGER NOT NULL,
  field TEXT NOT NULL,
  old_value TEXT NOT NULL,
  proposed_value TEXT NOT NULL,
  rationale TEXT NOT NULL,
  sample_count INTEGER NOT NULL,
  expected_delta_winrate REAL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  reviewed_at INTEGER
);

-- strategy_kill_switch: auto-disabled strategies
CREATE TABLE IF NOT EXISTS strategy_kill_switch (
  strategy TEXT PRIMARY KEY,
  killed_at INTEGER NOT NULL,
  reason TEXT NOT NULL,
  trigger_win_rate REAL NOT NULL,
  trigger_sample_size INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'killed' CHECK (status IN ('killed', 'reviewed_keep_killed', 'reviewed_reenabled')),
  reviewed_at INTEGER
);

-- portfolio_state: KV for equity / drawdown / halt flags
CREATE TABLE IF NOT EXISTS portfolio_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

-- schema_version: single-row migration tracking
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL
);
