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
    return request<{ message: string }>("/news/fetch", { method: "POST" });
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
};
