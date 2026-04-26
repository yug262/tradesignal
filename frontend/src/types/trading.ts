// Core trading system types — mirrors FastAPI backend models
// All timestamps are milliseconds (epoch ms) for safe JS number handling

export interface NewsArticleRef {
  id: string;
  title: string;
  description: string;
  source: string;
  published_at: number;       // milliseconds
  analyzed_at?: number | null; // milliseconds
  image_url?: string | null;
  impact_score: number;
  impact_summary?: string | null;
  executive_summary?: string | null;
  news_relevance?: string | null;
  news_category?: string | null;
  affected_symbols: string[];
  processing_status: string;
  raw_analysis_data: any;
  
  // New AI intelligence fields
  link?: string | null;
  market_bias?: string | null;
  signal_bucket?: string | null;
  primary_symbol?: string | null;
  affected_sectors?: string[];
  affected_stocks?: any;
  news_impact_level?: string | null;
  news_reason?: string | null;
  event_id?: string | null;
  event_title?: string | null;
  confidence?: number;
  horizon?: string | null;
  raw_full_data?: any;
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
export interface DiscoveryOutput {
  stock: {
    symbol: string;
    company_name: string | null;
    exchange: string;
  };
  news_analysis: {
    news_number: number;
    event_type: string;
    what_happened: string;
    confirmed_facts: string[];
    unknowns: string[];
    importance: string;
    importance_reason: string;
    impact_mechanism: string;
    bias: string;
    trading_thesis: string;
    invalidation: string;
    confidence: string;
  }[];
  combined_view: {
    final_bias: "BULLISH" | "BEARISH" | "MIXED" | "NEUTRAL";
    final_confidence: "LOW" | "MEDIUM" | "HIGH";
    executive_summary: string;
    why_this_stock_is_important_today: string;
    combined_trading_thesis: string;
    combined_invalidation: string;
    key_risks: string[];
    conflict_detected: boolean;
    conflict_reason: string;
    reasoning: {
      why_agent_gave_this_view: string;
      main_driver: string;
      supporting_points: string[];
      risk_points: string[];
      confidence_reason: string;
      what_agent_2_should_validate: string[];
    };
    should_pass_to_agent_2: boolean;
    pass_reason: string;
  };
  _source?: string;
  _model?: string;
}

// ── Agent 2 — Market Open Confirmation Output ────────────────────────────────
export interface ConfirmationOutput {
  validation: {
    status: "CONFIRMED" | "WEAKENED" | "INVALIDATED";
    reason: string;
  };
  thesis_check: {
    alignment: string;
    supporting_evidence: string[];
    contradicting_evidence: string[];
  };
  market_behavior: {
    price_behavior: string;
    volume_behavior: string;
    volatility_behavior: string;
  };
  trade_suitability: {
    mode: "INTRADAY" | "DELIVERY" | "NONE";
    holding_logic: string;
    priority: "HIGH" | "MEDIUM" | "LOW";
  };
  indicators_to_check: {
    trend: string[];
    momentum: string[];
    volatility: string[];
    volume: string[];
    pattern_recognition: string[];
    support_resistance: string[];
  };
  decision: {
    should_pass_to_agent_3: boolean;
    agent_3_instruction: string;
  };
  _source?: string;
  _model?: string;
}

// ── Agent 3 — Execution Planner Output ──────────────────────────────────────
export interface ExecutionOutput {
  _v2_execution_decision: {
    action: "ENTER_NOW" | "WAIT_FOR_PULLBACK" | "WAIT_FOR_BREAKOUT" | "AVOID";
    direction: "LONG" | "SHORT" | "NONE";
    trade_mode: "INTRADAY" | "DELIVERY" | "NONE";
    confidence: "HIGH" | "MEDIUM" | "LOW";
    reason: string;
  };
  trade_plan: {
    entry_price: number;
    stop_loss: number;
    target_price: number;
    risk_reward: number;
  };
  position_sizing: {
    quantity: number;
    capital_used: number;
    risk_amount: number;
    capital_used_pct: number;
  };
  order_payload: {
    transaction_type: "BUY" | "SELL";
    quantity: number;
    price: number;
  };
  technical_analysis_data?: any; // Data from Agent 2.5
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

// ── Paper Trading Types ──────────────────────────────────────────────────────

export interface PaperTrade {
  id: string;
  symbol: string;
  action: "BUY" | "SELL";
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  stop_loss: number;
  target_price: number;
  current_price: number | null;
  pnl: number;
  pnl_percentage: number;
  status: "OPEN" | "CLOSED" | "CANCELLED" | "PENDING";
  confidence_score: number;
  risk_level: string;
  trade_reason: string;
  exit_reason: string | null;
  signal_id: string | null;
  trade_mode: string;
  risk_reward: string | null;
  position_value: number;
  max_loss_at_sl: number;
  entry_time: number;
  exit_time: number | null;
  duration_ms: number | null;
  created_at: number;
  updated_at: number;
}

export interface Portfolio {
  total_capital: number;
  available_cash: number;
  used_cash: number;
  total_profit: number;
  total_loss: number;
  total_pnl: number;
  todays_pnl: number;
  win_rate: number;
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  winning_trades: number;
  losing_trades: number;
  updated_at: number | null;
}

export interface MarketSentiment {
  id: number;
  symbol: string;
  sector: string | null;
  sentiment: string | null;
  confidence_score: number;
  news_reason: string | null;
  event_strength: string | null;
  final_verdict: string | null;
  market_date: string | null;
  updated_at: number | null;
}

export interface AgentLog {
  id: number;
  agent_name: string;
  symbol: string | null;
  signal: string | null;
  confidence: number;
  message: string | null;
  details: Record<string, unknown> | null;
  trade_id: string | null;
  created_at: number;
}

export interface PaperTradingDashboard {
  portfolio: Portfolio;
  open_positions: PaperTrade[];
  recent_closed: PaperTrade[];
  recent_activity: AgentLog[];
}

export interface AnalyticsData {
  portfolio_growth: { date: string; cumulative_pnl: number; trade_pnl: number; symbol: string }[];
  daily_pnl: { date: string; pnl: number }[];
  win_loss: { wins: number; losses: number; total: number };
  exit_reasons: Record<string, number>;
  symbol_performance: { symbol: string; pnl: number; trades: number; wins: number }[];
}

