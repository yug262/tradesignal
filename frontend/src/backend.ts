/**
 * REST API client — replaces the ICP actor-based backend.ts.
 * All calls go to the FastAPI backend via /api/* endpoints.
 */

const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// Re-export types for backward compat with imports from "@/backend"
export type {
  NewsArticleRef,
  SystemConfig,
  ProcessingState,
  DashboardSummary,
  PaginatedResponse,
} from "./types/trading";

export const api = {
  // ─── News ──────────────────────────────────────────────────────────
  getNews(params: {
    page?: number;
    page_size?: number;
    symbol?: string | null;
    category?: string | null;
    min_impact?: number | null;
  }) {
    const qs = new URLSearchParams();
    qs.set("page", String(params.page ?? 0));
    qs.set("page_size", String(params.page_size ?? 20));
    if (params.symbol) qs.set("symbol", params.symbol);
    if (params.category) qs.set("category", params.category);
    if (params.min_impact != null) qs.set("min_impact", String(params.min_impact));
    return request<{
      items: import("./types/trading").NewsArticleRef[];
      page: number;
      page_size: number;
      total: number;
      has_more: boolean;
    }>(`/news?${qs.toString()}`);
  },

  getNewsById(id: string) {
    return request<import("./types/trading").NewsArticleRef | null>(`/news/${id}`);
  },

  getNewsCount() {
    return request<{ count: number }>("/news/count");
  },

  fetchNews() {
    return request<{ status: string; new_articles_saved?: number; message?: string }>("/agent/fetch-news", { method: "POST" });
  },

  getNewsGrouped() {
    return request<Record<string, import("./types/trading").NewsArticleRef[]>>("/news/grouped");
  },

  // ─── Config ────────────────────────────────────────────────────────
  getConfig() {
    return request<import("./types/trading").SystemConfig>("/config");
  },

  updateConfig(cfg: import("./types/trading").SystemConfig) {
    return request<{ success: boolean }>("/config", {
      method: "PUT",
      body: JSON.stringify(cfg),
    });
  },

  resetConfig() {
    return request<import("./types/trading").SystemConfig>("/config/reset", {
      method: "POST",
    });
  },

  // ─── Dashboard ─────────────────────────────────────────────────────
  getDashboardSummary() {
    return request<import("./types/trading").DashboardSummary>("/dashboard/summary");
  },

  getProcessingState() {
    return request<import("./types/trading").ProcessingState>("/dashboard/processing-state");
  },

  // ─── Stocks ────────────────────────────────────────────────────────
  getStocksGroupedAnalysis() {
    return request<any[]>("/stocks/grouped-analysis");
  },

  // ─── Agent ─────────────────────────────────────────────────────────
  triggerAgentRun() {
    return request<any>("/agent/run", { method: "POST" });
  },

  triggerConfirmationRun() {
    return request<any>("/agent/confirm", { method: "POST" });
  },

  triggerExecutionRun() {
    return request<any>("/agent/execute", { method: "POST" });
  },

  triggerTechnicalAnalysis() {
    return request<any>("/agent/technical-analysis", { method: "POST" });
  },

  triggerFullPipeline() {
    return request<any>("/agent/run-full-pipeline", { method: "POST" });
  },

  getAgentSignals(params?: { date?: string; signal_type?: string; trade_mode?: string; min_confidence?: number; confirmation_status?: string }) {
    const qs = new URLSearchParams();
    if (params?.date) qs.set("date", params.date);
    if (params?.signal_type) qs.set("signal_type", params.signal_type);
    if (params?.trade_mode) qs.set("trade_mode", params.trade_mode);
    if (params?.min_confidence != null) qs.set("min_confidence", String(params.min_confidence));
    if (params?.confirmation_status) qs.set("confirmation_status", params.confirmation_status);
    const query = qs.toString();
    return request<any>(`/agent/signals${query ? `?${query}` : ""}`);
  },

  getAgentStatus() {
    return request<any>("/agent/status");
  },

  // ─── Risk Monitor ──────────────────────────────────────────────────
  getRiskMonitorState() {
    return request<any>("/agent/risk-monitor");
  },

  triggerRiskMonitor() {
    return request<any>("/agent/risk-monitor", { method: "POST" });
  },

  // ─── Paper Trading ──────────────────────────────────────────────────
  getPaperTradingDashboard() {
    return request<import("./types/trading").PaperTradingDashboard>("/paper-trading/dashboard");
  },

  getOpenPositions() {
    return request<{ positions: import("./types/trading").PaperTrade[]; total: number }>("/paper-trading/positions/open");
  },

  getClosedPositions(limit = 50) {
    return request<{ positions: import("./types/trading").PaperTrade[]; total: number }>(`/paper-trading/positions/closed?limit=${limit}`);
  },

  getPortfolio() {
    return request<import("./types/trading").Portfolio>("/paper-trading/portfolio");
  },

  getPaperTrades(params?: { symbol?: string; status?: string; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.symbol) qs.set("symbol", params.symbol);
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return request<{ trades: import("./types/trading").PaperTrade[]; total: number }>(`/paper-trading/trades${query ? `?${query}` : ""}`);
  },

  createPaperTrade(trade: {
    symbol: string; action?: string; entry_price: number; stop_loss: number;
    target_price: number; quantity: number; trade_mode?: string;
    confidence_score?: number; risk_level?: string; trade_reason?: string;
    signal_id?: string; risk_reward?: string;
  }) {
    return request<{ success: boolean; trade_id?: string; error?: string }>("/paper-trading/trade", {
      method: "POST",
      body: JSON.stringify(trade),
    });
  },

  closePaperTrade(tradeId: string, exitPrice: number, exitReason = "MANUAL_EXIT") {
    return request<{ success: boolean; pnl?: number; error?: string }>(`/paper-trading/trade/${tradeId}/close`, {
      method: "POST",
      body: JSON.stringify({ exit_price: exitPrice, exit_reason: exitReason }),
    });
  },

  getAgentLogs(params?: { symbol?: string; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.symbol) qs.set("symbol", params.symbol);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return request<{ logs: import("./types/trading").AgentLog[]; total: number }>(`/paper-trading/logs${query ? `?${query}` : ""}`);
  },

  getMarketSentiment(date?: string) {
    const qs = date ? `?date=${date}` : "";
    return request<{ sentiments: import("./types/trading").MarketSentiment[]; total: number }>(`/paper-trading/sentiment${qs}`);
  },

  getPaperTradingAnalytics() {
    return request<import("./types/trading").AnalyticsData>("/paper-trading/analytics");
  },

  refreshPaperTradePrices() {
    return request<{ status: string; updated: number }>("/paper-trading/refresh-prices", { method: "POST" });
  },

  triggerPaperTradeMonitor() {
    return request<any>("/paper-trading/monitor", { method: "POST" });
  },

  // ─── Live News Agent ────────────────────────────────────────────────
  getLiveNewsEvents(params?: { date?: string; symbol?: string; only_trades?: boolean; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.date) qs.set("date", params.date);
    if (params?.symbol) qs.set("symbol", params.symbol);
    if (params?.only_trades) qs.set("only_trades", "true");
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return request<any>(`/agent/live-news/events${query ? `?${query}` : ""}`);
  },

  triggerLiveNewsMonitor() {
    return request<any>("/agent/live-news/run", { method: "POST" });
  },
};
