import { type ExtendedNewsFilter, FilterBar } from "@/components/FilterBar";
import { NewsArticleCard } from "@/components/NewsArticleCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useFilteredNews,
  useNewsList,
  useTriggerFetch,
} from "@/hooks/useNewsItems";
import { cn } from "@/lib/utils";
import type { NewsFilter } from "@/types/trading";
import { ChevronLeft, ChevronRight, Newspaper, RefreshCw } from "lucide-react";
import { useState } from "react";

const DEFAULT_FILTERS: ExtendedNewsFilter = {
  symbol: null,
  category: null,
  minImpact: null,
  dateRange: "all",
  relevance: "all",
  pageSize: 25,
};

function hasFilter(f: ExtendedNewsFilter): boolean {
  return !!(
    f.symbol ||
    (f.category && f.category !== "all") ||
    (f.minImpact && f.minImpact > 0) ||
    f.dateRange !== "all" ||
    f.relevance !== "all"
  );
}

// Convert extended filter to backend-compatible NewsFilter
function toBackendFilter(f: ExtendedNewsFilter): NewsFilter {
  return {
    symbol: f.symbol,
    category: f.category === "all" ? null : f.category,
    minImpact: f.minImpact,
  };
}

export function NewsFeedPage() {
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState<ExtendedNewsFilter>(DEFAULT_FILTERS);
  const triggerFetch = useTriggerFetch();

  const isFiltering = hasFilter(filters);
  const pageSize = filters.pageSize;
  const backendFilter = toBackendFilter(filters);

  const listQuery = useNewsList(page, pageSize);
  const filteredQuery = useFilteredNews(backendFilter);

  const isLoading = isFiltering ? filteredQuery.isLoading : listQuery.isLoading;
  const error = isFiltering ? filteredQuery.error : listQuery.error;

  // When filtering, use filtered data; otherwise use paginated list
  const allItems = isFiltering
    ? (filteredQuery.data ?? [])
    : (listQuery.data?.items ?? []);
  const totalAvailable = isFiltering
    ? allItems.length
    : (listQuery.data?.total ?? 0);

  const totalPages = Math.max(1, Math.ceil(totalAvailable / pageSize));

  // Reset page when filters change
  function handleFiltersChange(f: ExtendedNewsFilter) {
    setFilters(f);
    setPage(0);
  }

  return (
    <div className="flex flex-col h-full" data-ocid="news_feed.page">
      <div className="flex-1 overflow-y-auto">
        <div className="px-5 pb-5">
          {/* Sticky filter bar */}
          <FilterBar
            filters={filters}
            onChange={handleFiltersChange}
            totalShowing={allItems.length}
            totalAvailable={totalAvailable}
          />

          {/* Content area */}
          <div className="mt-3 space-y-3">
            {/* Fetch button row */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Newspaper size={11} className="text-muted-foreground" />
                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                  News Intelligence Feed
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 font-mono text-[10px] border-border text-muted-foreground hover:text-foreground"
                onClick={() => triggerFetch.mutate()}
                disabled={triggerFetch.isPending}
                type="button"
                data-ocid="news_feed.refresh_button"
              >
                <RefreshCw
                  size={10}
                  className={cn(
                    "mr-1.5",
                    triggerFetch.isPending && "animate-spin",
                  )}
                />
                {triggerFetch.isPending ? "Fetching..." : "FETCH NOW"}
              </Button>
            </div>

            {/* Articles list */}
            <div className="space-y-2" data-ocid="news_feed.list">
              {isLoading ? (
                [1, 2, 3, 4, 5, 6].map((i) => (
                  <div
                    key={i}
                    className="bg-card border border-border rounded p-4 space-y-3"
                    data-ocid={`news_feed.loading_state.${i}`}
                  >
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-5 w-16 rounded" />
                      <Skeleton className="h-4 w-12 rounded" />
                      <Skeleton className="h-4 w-12 rounded" />
                      <div className="ml-auto flex gap-2">
                        <Skeleton className="h-4 w-16 rounded" />
                        <Skeleton className="h-4 w-12 rounded" />
                      </div>
                    </div>
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-3 w-24" />
                    <div className="flex gap-1.5">
                      <Skeleton className="h-5 w-12 rounded" />
                      <Skeleton className="h-5 w-12 rounded" />
                    </div>
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-4/5" />
                  </div>
                ))
              ) : error ? (
                <div
                  className="bg-card border border-destructive/20 rounded p-8 text-center space-y-3"
                  data-ocid="news_feed.list.error_state"
                >
                  <p className="font-mono text-xs text-destructive">
                    Failed to load news feed
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="font-mono text-[10px] h-7 border-border"
                    onClick={() => triggerFetch.mutate()}
                    type="button"
                  >
                    <RefreshCw size={10} className="mr-1.5" />
                    Retry
                  </Button>
                </div>
              ) : allItems.length === 0 ? (
                <div
                  className="bg-card border border-border rounded p-12 text-center space-y-4"
                  data-ocid="news_feed.list.empty_state"
                >
                  <Newspaper
                    size={32}
                    className="mx-auto text-muted-foreground opacity-20"
                  />
                  <div>
                    <p className="font-mono text-xs text-muted-foreground">
                      No articles match your filters
                    </p>
                    <p className="font-mono text-[10px] text-muted-foreground opacity-50 mt-1">
                      {isFiltering
                        ? "Try adjusting or clearing your filters."
                        : "Trigger a fetch to populate the news feed."}
                    </p>
                  </div>
                  {!isFiltering && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="font-mono text-[10px] h-7 border-primary/30 text-primary hover:bg-primary/10"
                      onClick={() => triggerFetch.mutate()}
                      disabled={triggerFetch.isPending}
                      type="button"
                      data-ocid="news_feed.empty_fetch_button"
                    >
                      <RefreshCw
                        size={10}
                        className={cn(
                          "mr-1.5",
                          triggerFetch.isPending && "animate-spin",
                        )}
                      />
                      FETCH NEWS
                    </Button>
                  )}
                </div>
              ) : (
                allItems.map((article, idx) => (
                  <NewsArticleCard
                    key={article.id}
                    article={article}
                    idx={idx}
                    compact={false}
                  />
                ))
              )}
            </div>

            {/* Pagination (only when not filtering) */}
            {!isFiltering && totalAvailable > pageSize && (
              <div
                className="flex items-center justify-between pt-2 border-t border-border/30"
                data-ocid="news_feed.pagination"
              >
                <span className="font-mono text-[10px] text-muted-foreground">
                  Page{" "}
                  <span className="text-foreground font-semibold">
                    {page + 1}
                  </span>
                  {" / "}
                  <span className="text-foreground">{totalPages}</span>
                  {" · "}
                  <span className="opacity-60">{totalAvailable} total</span>
                </span>
                <div className="flex gap-1.5">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7 border-border"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    type="button"
                    data-ocid="news_feed.pagination_prev"
                  >
                    <ChevronLeft size={13} />
                  </Button>
                  {/* Page number buttons (show up to 5) */}
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const pageNum =
                      Math.max(0, Math.min(page - 2, totalPages - 5)) + i;
                    return (
                      <Button
                        key={pageNum}
                        variant={pageNum === page ? "default" : "outline"}
                        size="icon"
                        className={cn(
                          "h-7 w-7 font-mono text-[10px]",
                          pageNum === page
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border",
                        )}
                        onClick={() => setPage(pageNum)}
                        type="button"
                        data-ocid={`news_feed.pagination.page.${pageNum + 1}`}
                      >
                        {pageNum + 1}
                      </Button>
                    );
                  })}
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-7 w-7 border-border"
                    onClick={() =>
                      setPage((p) => Math.min(totalPages - 1, p + 1))
                    }
                    disabled={page >= totalPages - 1}
                    type="button"
                    data-ocid="news_feed.pagination_next"
                  >
                    <ChevronRight size={13} />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
