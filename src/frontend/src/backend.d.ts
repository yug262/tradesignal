import type { Principal } from "@icp-sdk/core/principal";
export interface Some<T> {
    __kind__: "Some";
    value: T;
}
export interface None {
    __kind__: "None";
}
export type Option<T> = Some<T> | None;
export interface SystemConfig {
    processing_mode: string;
    news_endpoint_url: string;
    use_mock_data: boolean;
    risk_per_trade_pct: number;
    min_rr: number;
    max_open_positions: bigint;
    capital: number;
    max_daily_loss_pct: number;
    polling_interval_mins: bigint;
}
export interface NewsArticleRef {
    id: string;
    title: string;
    news_category: string;
    source: string;
    executive_summary: string;
    image_url?: string;
    affected_symbols: Array<string>;
    impact_score: number;
    raw_analysis_data: string;
    analyzed_at: bigint;
    description: string;
    published_at: bigint;
    news_relevance: string;
    processing_status: string;
    impact_summary: string;
}
export interface ProcessingState {
    is_polling_active: boolean;
    last_processed_article_id?: string;
    articles_in_queue: bigint;
    current_mode: string;
    total_articles_processed: bigint;
    last_poll_timestamp: bigint;
}
export interface DashboardSummary {
    endpoint_status: string;
    no_trade_count: bigint;
    system_mode: string;
    total_articles_consumed: bigint;
    pending_candidates: bigint;
    last_refresh: bigint;
    articles_processed_today: bigint;
    active_opportunities: bigint;
}
export interface backendInterface {
    fetch_news(): Promise<string>;
    filter_news(symbol: string | null, category: string | null, min_impact: number | null): Promise<Array<NewsArticleRef>>;
    get_config(): Promise<SystemConfig>;
    get_dashboard_summary(): Promise<DashboardSummary>;
    get_news(page: bigint, page_size: bigint): Promise<Array<NewsArticleRef>>;
    get_news_by_id(id: string): Promise<NewsArticleRef | null>;
    get_processing_state(): Promise<ProcessingState>;
    get_total_news_count(): Promise<bigint>;
    reset_config(): Promise<SystemConfig>;
    update_config(cfg: SystemConfig): Promise<boolean>;
}
