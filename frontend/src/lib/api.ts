/**
 * Typed API wrapper functions — now uses REST fetch instead of ICP actor calls.
 */

import { api } from "@/backend";
import type {
  DashboardSummary,
  NewsArticleRef,
  NewsFilter,
  PaginatedResponse,
  ProcessingState,
  SystemConfig,
} from "@/types/trading";

// ─── News ────────────────────────────────────────────────────────────────────

export async function apiGetNews(
  page: number,
  pageSize: number,
): Promise<PaginatedResponse<NewsArticleRef>> {
  const res = await api.getNews({ page, page_size: pageSize });
  return {
    items: res.items,
    page: res.page,
    page_size: res.page_size,
    total: res.total,
    has_more: res.has_more,
  };
}

export async function apiGetNewsById(
  id: string,
): Promise<NewsArticleRef | null> {
  return api.getNewsById(id);
}

export async function apiFilterNews(
  filter: NewsFilter,
): Promise<NewsArticleRef[]> {
  const res = await api.getNews({
    page: 0,
    page_size: 100,
    symbol: filter.symbol,
    category: filter.category,
    min_impact: filter.minImpact,
  });
  return res.items;
}

export async function apiTriggerFetch(): Promise<string> {
  const res = await api.fetchNews();
  return res.message;
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

export async function apiGetDashboardSummary(): Promise<DashboardSummary | null> {
  return api.getDashboardSummary();
}

export async function apiGetProcessingState(): Promise<ProcessingState | null> {
  return api.getProcessingState();
}

// ─── Config ──────────────────────────────────────────────────────────────────

export async function apiGetConfig(): Promise<SystemConfig | null> {
  return api.getConfig();
}

export async function apiUpdateConfig(
  config: SystemConfig,
): Promise<boolean> {
  const res = await api.updateConfig(config);
  return res.success;
}

export async function apiResetConfig(): Promise<SystemConfig | null> {
  return api.resetConfig();
}

export async function apiResetProcessingState(): Promise<boolean> {
  // Phase 1: not yet implemented
  return false;
}
