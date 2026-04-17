import {
  apiFilterNews,
  apiGetConfig,
  apiGetDashboardSummary,
  apiGetNews,
  apiGetNewsById,
  apiGetProcessingState,
  apiResetConfig,
  apiResetProcessingState,
  apiTriggerFetch,
  apiUpdateConfig,
} from "@/lib/api";
import type { NewsFilter, SystemConfig } from "@/types/trading";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// ─── News list with pagination ───────────────────────────────────────────────

export function useNewsList(page = 0, pageSize = 20) {
  return useQuery({
    queryKey: ["news", page, pageSize],
    queryFn: () => apiGetNews(page, pageSize),
    staleTime: 30_000,
  });
}

// ─── Filtered news ───────────────────────────────────────────────────────────

export function useFilteredNews(filter: NewsFilter) {
  return useQuery({
    queryKey: ["news", "filtered", filter],
    queryFn: () => apiFilterNews(filter),
    staleTime: 30_000,
  });
}

// ─── Single news article ─────────────────────────────────────────────────────

export function useNewsItem(id: string | null) {
  return useQuery({
    queryKey: ["news", "item", id],
    queryFn: () => apiGetNewsById(id!),
    enabled: !!id,
    staleTime: 60_000,
  });
}

// ─── Dashboard summary ───────────────────────────────────────────────────────

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiGetDashboardSummary(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

// ─── Processing state ────────────────────────────────────────────────────────

export function useProcessingState() {
  return useQuery({
    queryKey: ["processing-state"],
    queryFn: () => apiGetProcessingState(),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}

// ─── System config ───────────────────────────────────────────────────────────

export function useSystemConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: () => apiGetConfig(),
    staleTime: 60_000,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: SystemConfig) => apiUpdateConfig(config),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useResetConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiResetConfig(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

export function useResetProcessingState() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiResetProcessingState(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["processing-state"] });
    },
  });
}

export function useTriggerFetch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiTriggerFetch(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["news"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["processing-state"] });
    },
  });
}
