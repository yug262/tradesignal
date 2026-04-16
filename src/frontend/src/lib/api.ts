import type { Backend } from "@/backend";
import type {
  DashboardSummary,
  NewsArticleRef,
  NewsFilter,
  PaginatedResponse,
  ProcessingState,
  SystemConfig,
} from "@/types/trading";

type Actor = Backend | null;

// ─── Typed API wrapper functions ────────────────────────────────────────────

export async function apiGetNews(
  actor: Actor,
  page: number,
  pageSize: number,
): Promise<PaginatedResponse<NewsArticleRef>> {
  if (!actor) return { items: [], page, pageSize, total: 0 };
  const [items, totalBig] = await Promise.all([
    actor.get_news(BigInt(page), BigInt(pageSize)),
    actor.get_total_news_count(),
  ]);
  return {
    items: items as NewsArticleRef[],
    page,
    pageSize,
    total: Number(totalBig),
  };
}

export async function apiGetNewsById(
  actor: Actor,
  id: string,
): Promise<NewsArticleRef | null> {
  if (!actor) return null;
  return (await actor.get_news_by_id(id)) as NewsArticleRef | null;
}

export async function apiFilterNews(
  actor: Actor,
  filter: NewsFilter,
): Promise<NewsArticleRef[]> {
  if (!actor) return [];
  const result = await actor.filter_news(
    filter.symbol,
    filter.category,
    filter.minImpact,
  );
  return result as NewsArticleRef[];
}

export async function apiTriggerFetch(actor: Actor): Promise<string> {
  if (!actor) return "no_actor";
  return actor.fetch_news();
}

export async function apiGetDashboardSummary(
  actor: Actor,
): Promise<DashboardSummary | null> {
  if (!actor) return null;
  return actor.get_dashboard_summary() as Promise<DashboardSummary>;
}

export async function apiGetConfig(actor: Actor): Promise<SystemConfig | null> {
  if (!actor) return null;
  return actor.get_config() as Promise<SystemConfig>;
}

export async function apiUpdateConfig(
  actor: Actor,
  config: SystemConfig,
): Promise<boolean> {
  if (!actor) return false;
  return actor.update_config(config);
}

export async function apiGetProcessingState(
  actor: Actor,
): Promise<ProcessingState | null> {
  if (!actor) return null;
  return actor.get_processing_state() as Promise<ProcessingState>;
}

export async function apiResetConfig(
  actor: Actor,
): Promise<SystemConfig | null> {
  if (!actor) return null;
  return actor.reset_config() as Promise<SystemConfig>;
}

export async function apiResetProcessingState(actor: Actor): Promise<boolean> {
  if (!actor) return false;
  // Phase 1: reset_processing_state not yet implemented in backend
  return false;
}
