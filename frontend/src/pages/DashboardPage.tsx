import { NewsArticleCard } from "@/components/NewsArticleCard";
import { StatWidget } from "@/components/StatWidget";
import { SystemHealthPanel } from "@/components/SystemHealthPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useDashboardSummary,
  useNewsList,
  useProcessingState,
  useSystemConfig,
  useTriggerFetch,
} from "@/hooks/useNewsItems";
import { cn, formatCount } from "@/lib/utils";
import { Link } from "@tanstack/react-router";
import {
  BarChart3,
  CheckCircle,
  Clock,
  Newspaper,
  RefreshCw,
  TrendingUp,
  Zap,
} from "lucide-react";

// ── Phase placeholder card ────────────────────────────────────────────────────
function PhasePlaceholder({
  title,
  description,
  phase,
  icon: Icon,
}: {
  title: string;
  description: string;
  phase: number;
  icon: typeof Newspaper;
}) {
  return (
    <div className="bg-card border border-border rounded p-5 space-y-3 relative overflow-hidden">
      {/* Phase watermark */}
      <div className="absolute top-3 right-3">
        <Badge
          variant="outline"
          className="font-mono text-[9px] px-2 py-0.5 border-chart-4/30 text-chart-4 bg-chart-4/5 uppercase tracking-widest"
        >
          Phase {phase}
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
          <Icon size={14} className="text-muted-foreground" />
        </div>
        <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
          {title}
        </span>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed opacity-70 pr-12">
        {description}
      </p>

      <div className="font-mono text-[9px] text-muted-foreground opacity-25 tracking-widest uppercase pt-1">
        ─── Module not initialized ───
      </div>
    </div>
  );
}

// ── Dashboard page ────────────────────────────────────────────────────────────
export function DashboardPage() {
  const { data: summary, isLoading: summaryLoading } = useDashboardSummary();
  const { data: procState } = useProcessingState();
  const { data: config } = useSystemConfig();
  const {
    data: newsData,
    isLoading: newsLoading,
    error: newsError,
  } = useNewsList(0, 5);
  const triggerFetch = useTriggerFetch();

  const isLive =
    summary?.system_mode === "LIVE" || summary?.system_mode === "live";
  const isMockData =
    summary?.endpoint_status === "MOCK_DATA" ||
    summary?.endpoint_status === "mock" ||
    config?.use_mock_data;

  function handleFetch() {
    triggerFetch.mutate();
  }

  const stats = [
    {
      label: "Total Articles Consumed",
      value: summary ? formatCount(summary.total_articles_consumed) : "—",
      icon: Newspaper,
      subtext: "all-time ingest",
      highlight: false,
    },
    {
      label: "Processed Today",
      value: summary ? formatCount(summary.articles_processed_today) : "—",
      icon: CheckCircle,
      subtext: "articles analyzed",
      highlight: (summary?.articles_processed_today ?? 0) > 0,
      badgeText:
        (summary?.articles_processed_today ?? 0) > 0
          ? "ACTIVE"
          : undefined,
      badgeVariant: "amber" as const,
    },
    {
      label: "Pending Candidates",
      value: summary ? formatCount(summary.pending_candidates) : "—",
      icon: Clock,
      subtext: "Phase 2 → event engine",
      badgeText: "P2",
      badgeVariant: "phase" as const,
    },
    {
      label: "System Mode",
      value: isLive ? "LIVE" : "PRE-MKT",
      icon: TrendingUp,
      subtext: procState?.current_mode ?? "—",
      highlight: isLive,
      badgeText: isLive ? "LIVE" : "BATCH",
      badgeVariant: isLive ? ("amber" as const) : ("muted" as const),
    },
  ];

  return (
    <div className="p-5 space-y-5" data-ocid="dashboard.page">
      {/* System status bar */}
      <div
        className="flex items-center gap-3 flex-wrap"
        data-ocid="dashboard.status_bar"
      >
        <div className="flex items-center gap-1.5">
          <Zap size={10} className="text-primary" />
          <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
            TradeSignal v1 · Phase 1 Active
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge
            variant="outline"
            className="font-mono text-[9px] px-2 py-0.5 border-border text-muted-foreground"
          >
            QUEUE: {procState ? formatCount(procState.articles_in_queue) : "—"}
          </Badge>
          <Badge
            variant="outline"
            className="font-mono text-[9px] px-2 py-0.5 border-border text-muted-foreground"
          >
            PROCESSED:{" "}
            {procState ? formatCount(procState.total_articles_processed) : "—"}
          </Badge>
          <Badge
            variant="outline"
            className={cn(
              "font-mono text-[9px] px-2 py-0.5",
              isMockData
                ? "border-chart-4/30 text-chart-4 bg-chart-4/5"
                : "border-chart-1/30 text-chart-1 bg-chart-1/5",
            )}
            data-ocid="dashboard.endpoint_badge"
          >
            {isMockData ? "● MOCK DATA" : "● LIVE ENDPOINT"}
          </Badge>
          {procState?.is_polling_active && (
            <Badge
              variant="outline"
              className="font-mono text-[9px] px-2 py-0.5 border-chart-1/30 text-chart-1 bg-chart-1/5"
            >
              <span className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-chart-1 animate-pulse" />
              POLLING
            </Badge>
          )}
        </div>
      </div>

      {/* Stats grid */}
      <div
        className="grid grid-cols-2 lg:grid-cols-4 gap-3"
        data-ocid="dashboard.stats"
      >
        {summaryLoading
          ? [1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="bg-card border border-border rounded p-4 space-y-2"
                data-ocid={`dashboard.stat.${i}`}
              >
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-8 w-14" />
                <Skeleton className="h-2.5 w-28" />
              </div>
            ))
          : stats.map((s, i) => (
              <StatWidget
                key={s.label}
                label={s.label}
                value={s.value}
                icon={s.icon}
                subtext={s.subtext}
                highlight={s.highlight}
                badgeText={s.badgeText}
                badgeVariant={s.badgeVariant}
                ocid={`dashboard.stat.${i + 1}`}
              />
            ))}
      </div>

      {/* Main content + sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* LEFT: Recent news intel */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Newspaper size={11} className="text-primary" />
              <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                Recent News Intel
              </span>
              {newsData && (
                <span className="font-mono text-[9px] text-muted-foreground opacity-50">
                  ({newsData.total} total)
                </span>
              )}
              <Badge
                variant="outline"
                className={cn(
                  "font-mono text-[9px] px-1.5 py-0 h-4 uppercase",
                  isMockData
                    ? "border-chart-4/30 text-chart-4 bg-chart-4/5"
                    : "border-chart-1/30 text-chart-1 bg-chart-1/5",
                )}
              >
                {isMockData ? "MOCK DATA" : "LIVE"}
              </Badge>
            </div>
            <Link
              to="/news-feed"
              className="font-mono text-[10px] text-primary hover:opacity-80 transition-colors uppercase tracking-wider"
              data-ocid="dashboard.view_all_news"
            >
              View All →
            </Link>
          </div>

          {/* Articles */}
          <div className="space-y-2" data-ocid="dashboard.news_list">
            {newsLoading ? (
              [1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="bg-card border border-border rounded p-3 space-y-2"
                  data-ocid={`dashboard.news_list.item.${i}`}
                >
                  <div className="flex gap-2">
                    <Skeleton className="h-5 w-10 rounded" />
                    <Skeleton className="h-4 flex-1" />
                    <Skeleton className="h-4 w-16" />
                  </div>
                  <Skeleton className="h-3 w-2/3" />
                </div>
              ))
            ) : newsError ? (
              <div
                className="bg-card border border-destructive/20 rounded p-6 text-center space-y-3"
                data-ocid="dashboard.news_list.error_state"
              >
                <p className="font-mono text-xs text-destructive">
                  Failed to load articles
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="font-mono text-[10px] h-7 border-border"
                  onClick={handleFetch}
                  type="button"
                  data-ocid="dashboard.error_retry_button"
                >
                  <RefreshCw size={10} className="mr-1.5" />
                  Retry
                </Button>
              </div>
            ) : newsData?.items.length === 0 ? (
              <div
                className="bg-card border border-border rounded p-10 text-center space-y-3"
                data-ocid="dashboard.news_list.empty_state"
              >
                <Newspaper
                  size={28}
                  className="mx-auto text-muted-foreground opacity-25"
                />
                <div>
                  <p className="font-mono text-xs text-muted-foreground">
                    No articles consumed yet
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground opacity-50 mt-1">
                    Trigger a fetch or enable polling to begin ingestion.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="font-mono text-[10px] h-7 border-primary/30 text-primary hover:bg-primary/10"
                  onClick={handleFetch}
                  disabled={triggerFetch.isPending}
                  type="button"
                  data-ocid="dashboard.empty_fetch_button"
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
            ) : (
              newsData?.items.map((article, idx) => (
                <NewsArticleCard
                  key={article.id}
                  article={article}
                  idx={idx}
                  compact
                />
              ))
            )}
          </div>
        </div>

        {/* RIGHT: System panel */}
        <div className="space-y-3">
          <div className="flex items-center gap-1.5">
            <Zap size={10} className="text-muted-foreground" />
            <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
              System Status
            </span>
          </div>
          <SystemHealthPanel
            processingState={procState}
            config={config}
            onFetchNow={handleFetch}
            isFetching={triggerFetch.isPending}
          />
        </div>
      </div>

      {/* Bottom phase placeholders */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <PhasePlaceholder
          title="Live Trade Opportunities"
          description="Event + technical engine output will appear here once Phase 2 and 3 modules are initialized. Filtered, scored candidates with RR, entry/SL/target."
          phase={2}
          icon={TrendingUp}
        />
        <PhasePlaceholder
          title="Market Regime Summary"
          description="Index state, sector heat, and regime analysis. Trend classification, volatility assessment, and macro risk context for all trade decisions."
          phase={3}
          icon={BarChart3}
        />
      </div>

      {/* Terminal footer */}
      <div className="font-mono text-[9px] text-muted-foreground opacity-25 text-center tracking-widest pb-1 border-t border-border/20 pt-3">
        ── PHASE 1 ACTIVE · EVENT ENGINE PHASE 2 · TECHNICAL ENGINE PHASE 3 ·
        DECISION ENGINE PHASE 4 ──
      </div>
    </div>
  );
}
