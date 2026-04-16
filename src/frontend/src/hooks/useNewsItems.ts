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
import { useBackend } from "./useBackend";

// ─── News list with pagination ───────────────────────────────────────────────

export function useNewsList(page = 0, pageSize = 20) {
  const { actor, isActorReady } = useBackend();
  return useQuery({
    queryKey: ["news", page, pageSize],
    queryFn: () => apiGetNews(actor, page, pageSize),
    enabled: isActorReady,
    staleTime: 30_000,
  });
}

// ─── Filtered news ───────────────────────────────────────────────────────────

export function useFilteredNews(filter: NewsFilter) {
  const { actor, isActorReady } = useBackend();
  return useQuery({
    queryKey: ["news", "filtered", filter],
    queryFn: () => apiFilterNews(actor, filter),
    enabled: isActorReady,
    staleTime: 30_000,
  });
}

// ─── Single news article ─────────────────────────────────────────────────────

export function useNewsItem(id: string | null) {
  const { actor, isActorReady } = useBackend();
  return useQuery({
    queryKey: ["news", "item", id],
    queryFn: () => apiGetNewsById(actor, id!),
    enabled: isActorReady && !!id,
    staleTime: 60_000,
  });
}

// ─── Dashboard summary ───────────────────────────────────────────────────────

export function useDashboardSummary() {
  const { actor, isActorReady } = useBackend();
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiGetDashboardSummary(actor),
    enabled: isActorReady,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

// ─── Processing state ────────────────────────────────────────────────────────

export function useProcessingState() {
  const { actor, isActorReady } = useBackend();
  return useQuery({
    queryKey: ["processing-state"],
    queryFn: () => apiGetProcessingState(actor),
    enabled: isActorReady,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}

// ─── System config ───────────────────────────────────────────────────────────

export function useSystemConfig() {
  const { actor, isActorReady } = useBackend();
  return useQuery({
    queryKey: ["config"],
    queryFn: () => apiGetConfig(actor),
    enabled: isActorReady,
    staleTime: 60_000,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useUpdateConfig() {
  const { actor } = useBackend();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (config: SystemConfig) => apiUpdateConfig(actor, config),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useResetConfig() {
  const { actor } = useBackend();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiResetConfig(actor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

export function useResetProcessingState() {
  const { actor } = useBackend();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiResetProcessingState(actor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["processing-state"] });
    },
  });
}

export function useTriggerFetch() {
  const { actor } = useBackend();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiTriggerFetch(actor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["news"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["processing-state"] });
    },
  });
}
