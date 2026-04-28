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
  ArrowRight,
  BarChart3,
  Brain,
  CheckCircle,
  Clock,
  ClipboardList,
  Activity,
  LineChart,
  Newspaper,
  RefreshCw,
  TrendingUp,
  Zap,
} from "lucide-react";

// ── Pipeline Step Card ───────────────────────────────────────────────────────
function PipelineStep({
  step,
  title,
  subtitle,
  icon: Icon,
  color,
  href,
  isLast,
}: {
  step: string;
  title: string;
  subtitle: string;
  icon: React.ElementType;
  color: string;
  href: string;
  isLast?: boolean;
}) {
  const colorMap: Record<string, string> = {
    violet: "bg-violet-500/10 border-violet-500/30 text-violet-400 hover:bg-violet-500/15",
    blue: "bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/15",
    cyan: "bg-cyan-500/10 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/15",
    indigo: "bg-indigo-500/10 border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/15",
  };
  const pillColor: Record<string, string> = {
    violet: "bg-violet-500/20 text-violet-400",
    blue: "bg-blue-500/20 text-blue-400",
    cyan: "bg-cyan-500/20 text-cyan-400",
    indigo: "bg-indigo-500/20 text-indigo-400",
  };
  const arrowColor: Record<string, string> = {
    violet: "text-violet-500/30",
    blue: "text-blue-500/30",
    cyan: "text-cyan-500/30",
    indigo: "text-indigo-500/30",
  };

  return (
    <div className="flex items-center gap-2">
      <Link
        to={href}
        className={cn(
          "flex-1 flex items-center gap-3 p-4 rounded-xl border transition-all duration-200 cursor-pointer group",
          colorMap[color],
        )}
      >
        <div className={cn("flex items-center justify-center w-10 h-10 rounded-lg", pillColor[color])}>
          <Icon size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] font-bold uppercase tracking-wider opacity-70">{step}</span>
          </div>
          <div className="text-sm font-semibold text-foreground truncate">{title}</div>
          <div className="text-[11px] text-muted-foreground truncate">{subtitle}</div>
        </div>
        <ArrowRight size={16} className="text-muted-foreground/40 group-hover:text-foreground/60 transition-colors shrink-0" />
      </Link>
      {!isLast && (
        <div className={cn("hidden xl:block shrink-0", arrowColor[color])}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M4 10h12M12 6l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      )}
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

  function handleFetch() {
    triggerFetch.mutate();
  }

  const stats = [
    {
      label: "Articles Consumed",
      value: summary ? formatCount(summary.total_articles_consumed) : "—",
      icon: Newspaper,
      subtext: "Total articles processed by the system",
      highlight: false,
    },
    {
      label: "Processed Today",
      value: summary ? formatCount(summary.articles_processed_today) : "—",
      icon: CheckCircle,
      subtext: "Articles analyzed in today's session",
      highlight: (summary?.articles_processed_today ?? 0) > 0,
      badgeText:
        (summary?.articles_processed_today ?? 0) > 0
          ? "ACTIVE"
          : undefined,
      badgeVariant: "green" as const,
    },
    {
      label: "Pending Signals",
      value: summary ? formatCount(summary.pending_candidates) : "—",
      icon: Clock,
      subtext: "Awaiting confirmation by Agent 2",
      badgeText: "Pipeline",
      badgeVariant: "phase" as const,
    },
    {
      label: "System Mode",
      value: isLive ? "LIVE" : "PRE-MKT",
      icon: TrendingUp,
      subtext: isLive ? "Market is open — live data active" : "Pre-market mode — batch analysis",
      highlight: isLive,
      badgeText: isLive ? "LIVE" : "BATCH",
      badgeVariant: isLive ? ("green" as const) : ("muted" as const),
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto" data-ocid="dashboard.page">

      {/* Welcome + Pipeline Overview */}
      <div className="space-y-2 animate-fade-up">
        <h2 className="font-display text-2xl font-bold tracking-tight text-foreground">
          Welcome to TradeSignal
        </h2>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Your AI-powered trading pipeline analyzes news events, validates them against live market data,
          runs technical analysis, and generates precise execution plans — all automatically.
        </p>
      </div>

      {/* Pipeline Visualizer */}
      <div className="animate-fade-up stagger-1">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={14} className="text-primary" />
          <span className="section-label">Trading Pipeline</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <PipelineStep
            step="Agent 1"
            title="News Discovery"
            subtitle="Pre-market 8:30 AM scan"
            icon={Brain}
            color="violet"
            href="/agent-signals"
          />
          <PipelineStep
            step="Agent 2"
            title="Market Validation"
            subtitle="9:15 AM open confirmation"
            icon={Activity}
            color="blue"
            href="/market-open"
          />
          <PipelineStep
            step="Agent 2.5"
            title="Technical Analysis"
            subtitle="TA-Lib indicator gating"
            icon={LineChart}
            color="cyan"
            href="/technical-analysis"
          />
          <PipelineStep
            step="Agent 3"
            title="Execution Planning"
            subtitle="Entry, SL & target levels"
            icon={ClipboardList}
            color="indigo"
            href="/execution-planner"
            isLast
          />
        </div>
      </div>

      {/* Stats grid */}
      <div
        className="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-fade-up stagger-2"
        data-ocid="dashboard.stats"
      >
        {summaryLoading
          ? [1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="bg-card border border-border rounded-xl p-5 space-y-3"
                data-ocid={`dashboard.stat.${i}`}
              >
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-16" />
                <Skeleton className="h-3 w-32" />
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
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-fade-up stagger-3">
        {/* LEFT: Recent news intel */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Newspaper size={14} className="text-primary" />
              <span className="section-label">
                Recent News Intel
              </span>
              {newsData && (
                <span className="font-mono text-[11px] text-muted-foreground/50">
                  ({newsData.total} total)
                </span>
              )}
              <Badge
                variant="outline"
                className="text-[10px] font-mono font-semibold px-2 py-0 h-5 rounded-full uppercase border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
              >
                LIVE
              </Badge>
            </div>
            <Link
              to="/news-feed"
              className="text-[12px] font-medium text-primary hover:opacity-80 transition-colors flex items-center gap-1"
              data-ocid="dashboard.view_all_news"
            >
              View All <ArrowRight size={12} />
            </Link>
          </div>

          {/* Articles */}
          <div className="space-y-2" data-ocid="dashboard.news_list">
            {newsLoading ? (
              [1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="bg-card border border-border rounded-xl p-4 space-y-2"
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
                className="bg-card border border-red-500/20 rounded-xl p-8 text-center space-y-3"
                data-ocid="dashboard.news_list.error_state"
              >
                <p className="text-sm text-red-400 font-medium">
                  Failed to load articles
                </p>
                <p className="text-xs text-muted-foreground">
                  Check that the backend server is running and accessible.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs h-8 border-border"
                  onClick={handleFetch}
                  type="button"
                  data-ocid="dashboard.error_retry_button"
                >
                  <RefreshCw size={12} className="mr-2" />
                  Retry
                </Button>
              </div>
            ) : newsData?.items.length === 0 ? (
              <div
                className="bg-card border border-border rounded-xl p-12 text-center space-y-4"
                data-ocid="dashboard.news_list.empty_state"
              >
                <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-secondary mx-auto">
                  <Newspaper
                    size={24}
                    className="text-muted-foreground/40"
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">
                    No articles consumed yet
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Trigger a fetch or enable auto-polling to begin ingesting news articles.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs h-8 border-primary/30 text-primary hover:bg-primary/10"
                  onClick={handleFetch}
                  disabled={triggerFetch.isPending}
                  type="button"
                  data-ocid="dashboard.empty_fetch_button"
                >
                  <RefreshCw
                    size={12}
                    className={cn(
                      "mr-2",
                      triggerFetch.isPending && "animate-spin",
                    )}
                  />
                  {triggerFetch.isPending ? "Fetching..." : "Fetch Now"}
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
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Zap size={14} className="text-muted-foreground" />
            <span className="section-label">
              System Status
            </span>
          </div>
          <SystemHealthPanel
            processingState={procState}
            config={config}
            onFetchNow={handleFetch}
            isFetching={triggerFetch.isPending}
          />

          {/* Quick Actions */}
          <div className="bg-card border border-border rounded-xl p-4 space-y-3">
            <span className="text-[12px] font-semibold text-foreground">Quick Actions</span>
            <div className="space-y-2">
              <Link to="/paper-trading" className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors group">
                <TrendingUp size={16} className="text-muted-foreground group-hover:text-primary transition-colors" />
                <div>
                  <div className="text-[13px] font-medium text-foreground">Paper Trading</div>
                  <div className="text-[11px] text-muted-foreground">View open positions & P&L</div>
                </div>
              </Link>
              <Link to="/opportunities" className="flex items-center gap-3 p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors group">
                <BarChart3 size={16} className="text-muted-foreground group-hover:text-primary transition-colors" />
                <div>
                  <div className="text-[13px] font-medium text-foreground">Opportunities</div>
                  <div className="text-[11px] text-muted-foreground">Live market scanner results</div>
                </div>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
