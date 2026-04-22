// Core trading system types — mirrors FastAPI backend models
// All timestamps are milliseconds (epoch ms) for safe JS number handling

export interface NewsArticleRef {
  id: string;
  title: string;
  description: string;
  source: string;
  published_at: number;       // milliseconds
  analyzed_at: number;        // milliseconds
  image_url?: string | null;
  impact_score: number;
  impact_summary: string;
  executive_summary: string;
  news_relevance: string;
  news_category: string;
  affected_symbols: string[];
  processing_status: string;
  raw_analysis_data: string;
}

export interface SystemConfig {
  capital: number;
  risk_per_trade_pct: number;
  max_open_positions: number;
  max_daily_loss_pct: number;
  min_rr: number;
  news_endpoint_url: string;
  polling_interval_mins: number;
  processing_mode: string;
  // Agent 3 position-sizing boundaries
  max_loss_per_trade_pct: number;    // Max % of capital to lose per trade
  max_capital_per_trade_pct: number; // Max % of capital allocated per trade
}

export interface ProcessingState {
  last_processed_article_id?: string | null;
  last_poll_timestamp: number;     // milliseconds
  total_articles_processed: number;
  current_mode: string;
  is_polling_active: boolean;
  articles_in_queue: number;
}

export interface DashboardSummary {
  total_articles_consumed: number;
  articles_processed_today: number;
  pending_candidates: number;
  active_opportunities: number;
  no_trade_count: number;
  system_mode: string;
  last_refresh: number;           // milliseconds
  endpoint_status: string;
}

export interface NewsFilter {
  symbol: string | null;
  category: string | null;
  minImpact: number | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
}

// ── Agent 1 — Discovery Layer Output ────────────────────────────────────────
// Answers: "What actually happened, and does it meaningfully matter?"
// Does NOT contain direction bias, trade preference, or watchlist decisions.
export interface DiscoveryOutput {
  event_summary: string;
  detailed_explanation: string;
  event_type: "corporate_event" | "macro" | "sector" | "regulatory" | "other";
  event_strength: "STRONG" | "MODERATE" | "WEAK";
  freshness: "FRESH" | "SLIGHTLY_OLD" | "OLD" | "REPEATED";
  directness: "DIRECT" | "INDIRECT" | "NONE";
  is_material: boolean;
  impact_analysis: string;
  key_positive_factors: string[];
  key_risks: string[];
  confidence: number;            // 0-100
  final_verdict: "IMPORTANT_EVENT" | "MODERATE_EVENT" | "MINOR_EVENT" | "NOISE";
  reasoning_summary: string;
  _source: string;
  _model: string;
}

// ── Agent 2 — Market Open Confirmation Output ────────────────────────────────
// Answers: "After the actual open, is there still usable edge?"
export interface ConfirmationOutput {
  decision: "TRADE" | "NO TRADE";
  trade_mode: "INTRADAY" | "DELIVERY" | "NONE";
  direction: "BULLISH" | "BEARISH" | "NEUTRAL" | "MIXED";
  remaining_impact: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  priced_in_status: "NOT PRICED IN" | "PARTIALLY PRICED IN" | "FULLY PRICED IN" | "UNCLEAR";
  priority: "HIGH" | "MEDIUM" | "LOW";
  confidence: number;            // 0-100
  why_tradable_or_not: string;
  key_confirmations: string[];
  warning_flags: string[];
  invalid_if: string[];
  final_summary: string;
  _source?: string;
  _model?: string;
}

// ── Agent 3 — Execution Planner Output ──────────────────────────────────────
// Answers: "Can this be traded right now, and how safely?"
export interface ExecutionOutput {
  action: "BUY" | "SELL" | "WAIT" | "AVOID";
  execution_decision:
    | "ENTER NOW"
    | "WAIT FOR BREAKOUT"
    | "WAIT FOR PULLBACK"
    | "AVOID CHASE"
    | "NO TRADE";
  trade_mode: "INTRADAY" | "DELIVERY" | "NONE";
  confidence: number;
  entry_plan: {
    entry_type: "MARKET" | "BREAKOUT" | "PULLBACK" | "NONE";
    entry_price: number;
    condition: string;
  };
  stop_loss: {
    price: number;
    reason: string;
  };
  target: {
    price: number;
    reason: string;
  };
  position_sizing: {
    position_size_shares: number;
    position_size_inr: number;
    risk_per_share: number;
    max_loss_at_sl: number;
    capital_used_pct: number;
    sizing_note: string;
  };
  risk_reward: string;
  invalidation: string;
  why_now_or_why_wait: string;
  final_summary: string;
  _source?: string;
  _model?: string;
}

// ── Trade Signal (DB record) ─────────────────────────────────────────────────
export interface TradeSignal {
  id: string;
  symbol: string;
  signal_type: string;          // WATCH | NO_TRADE | BUY | SELL
  trade_mode: string;           // NONE (Agent 1) | INTRADAY | DELIVERY (Agent 2+)
  entry_price: number | null;
  stop_loss: number | null;
  target_price: number | null;
  risk_reward: number | null;
  confidence: number;
  reasoning: DiscoveryOutput | null;         // Agent 1 Discovery output
  news_article_ids: string[];
  stock_snapshot: Record<string, unknown> | null;
  generated_at: number;
  market_date: string;
  status: string;
  // Agent 2
  confirmation_status: string;
  confirmed_at: number | null;
  confirmation_data: ConfirmationOutput | null;
  // Agent 3
  execution_status: string;
  executed_at: number | null;
  execution_data: ExecutionOutput | null;
}

// ── Utility Types ─────────────────────────────────────────────────────────────
export type SystemMode = "PRE-MARKET" | "LIVE" | "BATCH";
export type EndpointStatus = "LIVE_ENDPOINT" | "OFFLINE";
export type ProcessingStatus =
  | "new"
  | "analyzed"
  | "no_trade"
  | "candidate"
  | "planned";
export type ImpactLevel = "high" | "medium" | "low";

export function getImpactLevel(score: number): ImpactLevel {
  if (score >= 7) return "high";
  if (score >= 4) return "medium";
  return "low";
}

export function msToDate(ts: number): Date {
  return new Date(ts);
}

export function formatTimestamp(ts: number): string {
  const d = msToDate(ts);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
