module {

  // ─── News Article Reference ────────────────────────────────────────────────

  public type NewsArticleRef = {
    id : Text;
    title : Text;
    description : Text;
    source : Text;
    published_at : Int;        // nanoseconds
    analyzed_at : Int;         // nanoseconds
    image_url : ?Text;
    impact_score : Float;      // 1.0–10.0
    impact_summary : Text;
    executive_summary : Text;
    news_relevance : Text;     // "high" | "medium" | "low"
    news_category : Text;      // "earnings" | "merger" | "regulatory" | "macro" | "product"
    affected_symbols : [Text];
    processing_status : Text;  // "pending" | "processed" | "skipped"
    raw_analysis_data : Text;  // JSON string
  };

  // ─── System Configuration ──────────────────────────────────────────────────

  public type SystemConfig = {
    capital : Float;               // default 100000.0
    risk_per_trade_pct : Float;    // default 1.0
    max_open_positions : Nat;      // default 5
    max_daily_loss_pct : Float;    // default 3.0
    min_rr : Float;                // default 1.5
    news_endpoint_url : Text;
    polling_interval_mins : Nat;   // default 5
    use_mock_data : Bool;          // default true
    processing_mode : Text;        // "pre_market" | "live"
  };

  // ─── Processing State ──────────────────────────────────────────────────────

  public type ProcessingState = {
    last_processed_article_id : ?Text;
    last_poll_timestamp : Int;
    total_articles_processed : Nat;
    current_mode : Text;
    is_polling_active : Bool;
    articles_in_queue : Nat;
  };

  // ─── Dashboard Summary ─────────────────────────────────────────────────────

  public type DashboardSummary = {
    total_articles_consumed : Nat;
    articles_processed_today : Nat;
    pending_candidates : Nat;
    active_opportunities : Nat;
    no_trade_count : Nat;
    system_mode : Text;
    last_refresh : Int;
    endpoint_status : Text;  // "connected" | "mock" | "error"
  };

};
