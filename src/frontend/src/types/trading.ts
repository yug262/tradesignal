// Core trading system types — mirrors Motoko backend types with JS-friendly conversions

export interface NewsArticleRef {
  id: string;
  title: string;
  description: string;
  source: string;
  published_at: bigint;
  analyzed_at: bigint;
  image_url?: string;
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
  max_open_positions: bigint;
  max_daily_loss_pct: number;
  min_rr: number;
  news_endpoint_url: string;
  polling_interval_mins: bigint;
  use_mock_data: boolean;
  processing_mode: string;
}

export interface ProcessingState {
  last_processed_article_id?: string;
  last_poll_timestamp: bigint;
  total_articles_processed: bigint;
  current_mode: string;
  is_polling_active: boolean;
  articles_in_queue: bigint;
}

export interface DashboardSummary {
  total_articles_consumed: bigint;
  articles_processed_today: bigint;
  pending_candidates: bigint;
  active_opportunities: bigint;
  no_trade_count: bigint;
  system_mode: string;
  last_refresh: bigint;
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
  pageSize: number;
  total: number;
}

export type SystemMode = "PRE-MARKET" | "LIVE" | "BATCH";
export type EndpointStatus = "MOCK_DATA" | "LIVE_ENDPOINT" | "OFFLINE";
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

export function bigIntToDate(ts: bigint): Date {
  // Backend timestamps are in nanoseconds
  return new Date(Number(ts / 1_000_000n));
}

export function formatTimestamp(ts: bigint): string {
  const d = bigIntToDate(ts);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
