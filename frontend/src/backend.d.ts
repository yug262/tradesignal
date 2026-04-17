/**
 * REST API client type declarations.
 * Re-exports types from types/trading.ts for backward compatibility.
 */

export type {
  NewsArticleRef,
  SystemConfig,
  ProcessingState,
  DashboardSummary,
  PaginatedResponse,
} from "./types/trading";

export { api } from "./backend";
