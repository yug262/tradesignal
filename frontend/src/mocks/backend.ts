/**
 * Frontend mock backend — for unit testing / offline dev.
 * Mirrors the REST API response shapes with number timestamps (milliseconds).
 */

import type { NewsArticleRef, SystemConfig, DashboardSummary, ProcessingState } from "../types/trading";

const mockArticles: NewsArticleRef[] = [
  {
    id: "art-001",
    title: "Fed signals potential rate cut in Q2 as inflation cools",
    news_category: "Macro",
    source: "Reuters",
    executive_summary: "Federal Reserve officials hint at possible rate reductions in Q2 2026 following easing CPI data, boosting equity outlook.",
    affected_symbols: ["SPY", "QQQ", "TLT"],
    impact_score: 0.87,
    raw_analysis_data: JSON.stringify({ sentiment: "bullish", confidence: 0.82 }),
    analyzed_at: Date.now(),
    description: "The Federal Reserve is signaling it may begin cutting interest rates in the second quarter of 2026 as inflation data continues to cool below target levels.",
    published_at: Date.now() - 3600000,
    news_relevance: "HIGH",
    processing_status: "PROCESSED",
    impact_summary: "Bullish for equities, bearish for USD. High impact macro event."
  },
  {
    id: "art-002",
    title: "NVDA earnings beat by 18% — data center revenue surges",
    news_category: "Earnings",
    source: "Bloomberg",
    executive_summary: "NVIDIA Q1 2026 earnings exceeded estimates by 18% driven by accelerating data center AI infrastructure demand.",
    affected_symbols: ["NVDA", "AMD", "SMCI"],
    impact_score: 0.94,
    raw_analysis_data: JSON.stringify({ sentiment: "strongly_bullish", confidence: 0.91 }),
    analyzed_at: Date.now(),
    description: "NVIDIA posted record quarterly earnings, beating analyst estimates by 18%. Data center revenue grew 120% year-over-year, fueled by continued AI infrastructure build-out.",
    published_at: Date.now() - 7200000,
    news_relevance: "CRITICAL",
    processing_status: "PROCESSED",
    impact_summary: "Strong buy catalyst for NVDA. Sector rotation into AI chip names expected."
  },
  {
    id: "art-003",
    title: "TSLA delivery miss raises demand concerns, shares drop pre-market",
    news_category: "Company News",
    source: "WSJ",
    executive_summary: "Tesla reported Q1 deliveries 12% below analyst consensus, sparking demand concerns and pre-market sell-off.",
    affected_symbols: ["TSLA", "RIVN", "LCID"],
    impact_score: 0.78,
    raw_analysis_data: JSON.stringify({ sentiment: "bearish", confidence: 0.76 }),
    analyzed_at: Date.now(),
    description: "Tesla's Q1 2026 delivery figures came in 12% below Wall Street expectations, raising concerns about weakening EV demand globally.",
    published_at: Date.now() - 1800000,
    news_relevance: "HIGH",
    processing_status: "PROCESSED",
    impact_summary: "Bearish for TSLA. Short catalyst. Watch for sympathy weakness in EV names."
  },
  {
    id: "art-004",
    title: "Apple quietly acquires AI startup for $2.1B — supply chain rumored",
    news_category: "M&A",
    source: "The Information",
    executive_summary: "Apple confirmed acquisition of AI-focused chip design startup in a $2.1B deal, expanding its in-house silicon roadmap.",
    affected_symbols: ["AAPL", "QCOM"],
    impact_score: 0.61,
    raw_analysis_data: JSON.stringify({ sentiment: "mildly_bullish", confidence: 0.58 }),
    analyzed_at: Date.now(),
    description: "Apple has confirmed it has acquired a private AI chip design startup for approximately $2.1 billion, a move expected to accelerate its in-house silicon development.",
    published_at: Date.now() - 5400000,
    news_relevance: "MEDIUM",
    processing_status: "PROCESSED",
    impact_summary: "Mildly bullish for AAPL long-term. Neutral near-term catalyst."
  },
  {
    id: "art-005",
    title: "Oil surges 4% after OPEC+ surprise production cut announcement",
    news_category: "Commodity",
    source: "FT",
    executive_summary: "OPEC+ announced an unexpected 500K barrel/day production cut, driving crude oil prices up sharply in Asian trading.",
    affected_symbols: ["XOM", "CVX", "USO", "COP"],
    impact_score: 0.83,
    raw_analysis_data: JSON.stringify({ sentiment: "bullish", confidence: 0.80 }),
    analyzed_at: Date.now(),
    description: "OPEC+ surprised markets with a 500,000 barrel per day production cut effective immediately, sending WTI crude prices up 4% in early Asian trading.",
    published_at: Date.now() - 900000,
    news_relevance: "HIGH",
    processing_status: "PROCESSED",
    impact_summary: "Bullish for energy sector. Watch XOM, CVX for intraday momentum plays."
  }
];

const mockConfig: SystemConfig = {
  processing_mode: "EVENT",
  news_endpoint_url: "https://api.newsprovider.example/v1/news",
  use_mock_data: true,
  risk_per_trade_pct: 1.5,
  min_rr: 2.0,
  max_open_positions: 5,
  capital: 50000,
  max_daily_loss_pct: 3.0,
  polling_interval_mins: 15
};

const mockDashboardSummary: DashboardSummary = {
  endpoint_status: "CONNECTED",
  no_trade_count: 12,
  system_mode: "EVENT",
  total_articles_consumed: 1247,
  pending_candidates: 3,
  last_refresh: Date.now(),
  articles_processed_today: 47,
  active_opportunities: 4
};

const mockProcessingState: ProcessingState = {
  is_polling_active: true,
  last_processed_article_id: "art-005",
  articles_in_queue: 3,
  current_mode: "EVENT",
  total_articles_processed: 1247,
  last_poll_timestamp: Date.now() - 60000
};

export {
  mockArticles,
  mockConfig,
  mockDashboardSummary,
  mockProcessingState,
};
