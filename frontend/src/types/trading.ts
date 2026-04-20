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
  // Backend timestamps are in milliseconds
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
