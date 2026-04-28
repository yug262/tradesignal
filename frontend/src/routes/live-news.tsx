import { useEffect, useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api } from "@/backend";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  RefreshCw,
  Clock,
  ChevronDown,
  ChevronUp,
  Zap,
  ArrowUpCircle,
  ArrowDownCircle,
  Minus,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Radio,
  TrendingUp,
  TrendingDown,
  Shield,
  Target,
} from "lucide-react";

export const Route = createFileRoute("/live-news")({
  component: LiveNewsPage,
});

function LiveNewsPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getLiveNewsEvents({ limit: 100 });
      setData(result);
    } catch (err) {
      console.error("Failed to load live news events", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEvents();
    // Auto-refresh every 60 seconds
    const interval = setInterval(loadEvents, 60000);
    return () => clearInterval(interval);
  }, [loadEvents]);

  const triggerRun = async () => {
    setRunning(true);
    try {
      await api.triggerLiveNewsMonitor();
      await loadEvents();
    } catch (err) {
      console.error("Live News Monitor run failed", err);
    } finally {
      setRunning(false);
    }
  };

  const events = data?.events || [];
  const summary = data?.summary || {};

  // Filtering
  const filtered = events.filter((e: any) => {
    if (filter === "TRADE") return e.should_trade === true;
    if (filter === "NO_TRADE") return e.should_trade === false;
    if (filter === "TRIGGERED") return e.agent3_triggered === true;
    return true;
  });

  const tradeCount = events.filter((e: any) => e.should_trade).length;
  const noTradeCount = events.filter((e: any) => !e.should_trade).length;
  const triggeredCount = events.filter((e: any) => e.agent3_triggered).length;

  const biasIcon = (bias: string) => {
    const b = (bias || "").toUpperCase();
    if (b === "BULLISH") return <ArrowUpCircle size={14} className="text-emerald-400" />;
    if (b === "BEARISH") return <ArrowDownCircle size={14} className="text-red-400" />;
    return <Minus size={14} className="text-zinc-400" />;
  };

  const biasColor = (bias: string) => {
    const b = (bias || "").toUpperCase();
    if (b === "BULLISH") return "text-emerald-400";
    if (b === "BEARISH") return "text-red-400";
    return "text-zinc-400";
  };

  const confidenceBadge = (confidence: number) => {
    if (confidence >= 75) return "border-emerald-500/30 text-emerald-400 bg-emerald-500/5";
    if (confidence >= 65) return "border-amber-500/30 text-amber-400 bg-amber-500/5";
    if (confidence >= 50) return "border-orange-500/30 text-orange-400 bg-orange-500/5";
    return "border-red-500/30 text-red-400 bg-red-500/5";
  };

  return (
    <div className="p-5 space-y-5" data-ocid="live-news.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-amber-500" />
          <span className="font-mono text-[12px] font-bold text-foreground uppercase tracking-widest">
            Live News Agent
          </span>
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 h-4 border-amber-500/30 text-amber-400 bg-amber-500/5 ml-2">
            INTRADAY MONITOR
          </Badge>
          <div className="flex items-center gap-1 ml-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="font-mono text-[9px] text-emerald-400">LIVE</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <Badge variant="outline" className="font-mono text-[9px] px-2 py-0.5 border-border text-muted-foreground">
              <Clock size={8} className="mr-1" />
              {data.market_date} · {events.length} events
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={loadEvents}
            disabled={loading}
            className="font-mono text-[10px] h-6 border-border"
          >
            <RefreshCw size={10} className={`mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={triggerRun}
            disabled={running}
            className="font-mono text-[10px] h-6 bg-amber-600 text-white hover:bg-amber-700 shadow-[0_0_15px_rgba(245,158,11,0.3)]"
          >
            {running ? (
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Running...</>
            ) : (
              <><Zap size={10} className="mr-1" /> Run Live Scan</>
            )}
          </Button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-4">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong>How it works:</strong> The Live News Agent runs every 60 seconds during market hours (09:15–15:30 IST).
          It fetches breaking news, runs a combined Gemini analysis (Agent 1+2 fast prompt), and triggers the full pipeline
          (Agent 2.5 → 3) when <strong className="text-emerald-400">confidence ≥ 65</strong> and <strong className="text-emerald-400">should_trade = true</strong>.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "TOTAL", count: events.length, icon: <Radio size={16} />, color: "text-blue-400", bg: "bg-blue-500/5 border-blue-500/20", filterKey: "ALL" },
          { label: "TRADE", count: tradeCount, icon: <Target size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20", filterKey: "TRADE" },
          { label: "NO TRADE", count: noTradeCount, icon: <XCircle size={16} />, color: "text-zinc-400", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "NO_TRADE" },
          { label: "PIPELINE TRIGGERED", count: triggeredCount, icon: <Zap size={16} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20", filterKey: "TRIGGERED" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn(
              "border rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-all hover:scale-[1.02]",
              item.bg,
              filter === item.filterKey && "ring-1 ring-primary/40"
            )}
            onClick={() => setFilter(filter === item.filterKey ? "ALL" : item.filterKey)}
          >
            <div className={item.color}>{item.icon}</div>
            <div>
              <div className={cn("text-xl font-bold font-mono tabular-nums", item.color)}>{item.count}</div>
              <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">{item.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filter Bar */}
      <div className="flex items-center justify-between flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest mr-1">Filter:</span>
          {["ALL", "TRADE", "NO_TRADE", "TRIGGERED"].map((s) => (
            <Badge
              key={s}
              variant="outline"
              className={cn(
                "font-mono text-[9px] px-2 py-0.5 cursor-pointer transition-all",
                filter === s
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/30"
              )}
              onClick={() => setFilter(s)}
            >
              {s.replace("_", " ")}
            </Badge>
          ))}
        </div>
        <span className="font-mono text-[9px] text-muted-foreground">
          Showing {filtered.length} of {events.length} events
        </span>
      </div>

      {/* Event Cards */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-card border border-border rounded-lg p-5 space-y-3">
              <div className="flex justify-between">
                <Skeleton className="h-6 w-32" />
                <Skeleton className="h-5 w-20" />
              </div>
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-lg p-12 text-center space-y-3">
          <Radio size={32} className="mx-auto text-muted-foreground opacity-20" />
          <p className="font-mono text-xs text-muted-foreground">No live news events today</p>
          <p className="font-mono text-[10px] text-muted-foreground opacity-50">
            The Live Agent runs every minute during market hours. Events will appear here automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((event: any) => {
            const isExpanded = expandedId === event.id;
            const bias = event.market_bias || "NEUTRAL";
            const confidence = event.confidence || 0;
            const shouldTrade = event.should_trade;
            const triggered = event.agent3_triggered;

            return (
              <div
                key={event.id}
                className={cn(
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  shouldTrade
                    ? triggered
                      ? "border-amber-500/30"
                      : "border-emerald-500/20"
                    : "border-border opacity-80"
                )}
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : event.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Bias */}
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                        {biasIcon(bias)}
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{event.symbol}</h3>
                        <div className={cn("font-mono text-[9px] uppercase tracking-widest font-bold", biasColor(bias))}>
                          {bias}
                        </div>
                      </div>

                      {/* Trade decision */}
                      <div className="ml-2 border-l border-border/50 pl-3 flex items-center gap-2">
                        {shouldTrade ? (
                          <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5">
                            <CheckCircle2 size={10} className="mr-1" />
                            TRADE
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5">
                            <XCircle size={10} className="mr-1" />
                            NO TRADE
                          </Badge>
                        )}
                        {triggered && (
                          <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5 animate-pulse">
                            <Zap size={10} className="mr-1" />
                            PIPELINE
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* Right: Meta */}
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Confidence</div>
                        <Badge variant="outline" className={cn("font-mono text-[10px] font-bold tabular-nums", confidenceBadge(confidence))}>
                          {confidence}%
                        </Badge>
                      </div>
                      {event.current_price && (
                        <div className="text-right hidden md:block">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase">LTP</div>
                          <div className="font-mono text-xs font-bold text-foreground">₹{event.current_price?.toFixed(2)}</div>
                        </div>
                      )}
                      <div className="text-right hidden md:block">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Time</div>
                        <div className="font-mono text-[10px] text-muted-foreground">{event.triggered_time || "—"}</div>
                      </div>
                      <div className="text-muted-foreground">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </div>
                    </div>
                  </div>

                  {/* One-line summary */}
                  {event.what_happened && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1 italic">
                      {event.what_happened}
                    </p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    {/* Key Fields Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      <div className={cn("bg-background/50 rounded p-3 border border-l-2", shouldTrade ? "border-emerald-500/30 border-l-emerald-500" : "border-zinc-500/30 border-l-zinc-500")}>
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Decision</div>
                        <div className={cn("font-mono text-sm font-bold", shouldTrade ? "text-emerald-400" : "text-zinc-400")}>
                          {shouldTrade ? "TRADE" : "NO TRADE"}
                        </div>
                      </div>
                      <div className="bg-background/50 rounded p-3 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Market Bias</div>
                        <div className={cn("font-mono text-sm font-bold", biasColor(bias))}>{bias}</div>
                      </div>
                      <div className="bg-background/50 rounded p-3 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Reaction</div>
                        <div className="font-mono text-sm font-bold text-foreground">
                          {event.market_reacted ? (
                            <span className="text-amber-400">{event.reaction_magnitude_pct?.toFixed(1)}%</span>
                          ) : (
                            <span className="text-zinc-400">None</span>
                          )}
                        </div>
                      </div>
                      <div className="bg-background/50 rounded p-3 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Prices</div>
                        <div className="font-mono text-xs text-foreground">
                          {event.publish_time_price && event.current_price ? (
                            <>
                              <span className="text-muted-foreground">₹{event.publish_time_price?.toFixed(0)}</span>
                              <span className="mx-1">→</span>
                              <span className="font-bold">₹{event.current_price?.toFixed(0)}</span>
                            </>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Analysis Sections */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      {/* What Happened */}
                      <div className="p-3 rounded border border-border/50 bg-background/50 shadow-sm border-l-2 border-l-blue-500">
                        <div className="font-mono text-[9px] text-blue-400 uppercase tracking-widest font-semibold mb-1">What Happened</div>
                        <p className="text-xs text-foreground leading-relaxed">{event.what_happened || "—"}</p>
                      </div>

                      {/* What Is Confirmed */}
                      <div className="p-3 rounded border border-border/50 bg-background/50 shadow-sm border-l-2 border-l-cyan-500">
                        <div className="font-mono text-[9px] text-cyan-400 uppercase tracking-widest font-semibold mb-1">What Is Confirmed</div>
                        <p className="text-xs text-foreground leading-relaxed">{event.what_is_confirmed || "—"}</p>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      {/* Why It Matters */}
                      <div className="p-3 rounded border border-border/50 bg-background/50 shadow-sm border-l-2 border-l-violet-500">
                        <div className="font-mono text-[9px] text-violet-400 uppercase tracking-widest font-semibold mb-1">Why This News Matters</div>
                        <p className="text-xs text-foreground leading-relaxed">{event.why_news_matters || "—"}</p>
                      </div>

                      {/* Trading Thesis */}
                      {event.trading_thesis && (
                        <div className={cn(
                          "p-3 rounded border shadow-sm border-l-2",
                          shouldTrade
                            ? "bg-emerald-500/5 border-emerald-500/20 border-l-emerald-500"
                            : "bg-background/50 border-border/50 border-l-zinc-500"
                        )}>
                          <div className={cn(
                            "font-mono text-[9px] uppercase tracking-widest font-semibold mb-1",
                            shouldTrade ? "text-emerald-400" : "text-zinc-400"
                          )}>
                            Trading Thesis
                          </div>
                          <p className="text-xs text-foreground leading-relaxed">{event.trading_thesis}</p>
                        </div>
                      )}
                    </div>

                    {/* Invalidation & Remaining Move */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {event.invalidation_logic && (
                        <div className="p-3 rounded border border-red-500/20 bg-red-500/5 shadow-sm border-l-2 border-l-red-500">
                          <div className="font-mono text-[9px] text-red-400 uppercase tracking-widest font-semibold mb-1">
                            <AlertTriangle size={10} className="inline mr-1" />
                            Invalidation
                          </div>
                          <p className="text-xs text-foreground leading-relaxed">{event.invalidation_logic}</p>
                        </div>
                      )}
                      {event.remaining_move_estimate && (
                        <div className="p-3 rounded border border-border/50 bg-background/50 shadow-sm border-l-2 border-l-amber-500">
                          <div className="font-mono text-[9px] text-amber-400 uppercase tracking-widest font-semibold mb-1">Remaining Move Estimate</div>
                          <p className="text-xs text-foreground leading-relaxed">{event.remaining_move_estimate}</p>
                        </div>
                      )}
                    </div>

                    {/* Trade Reason */}
                    {event.trade_reason && (
                      <div className={cn(
                        "p-3 rounded border shadow-sm",
                        shouldTrade ? "bg-emerald-500/5 border-emerald-500/20" : "bg-zinc-500/5 border-zinc-500/20"
                      )}>
                        <div className={cn(
                          "font-mono text-[9px] uppercase tracking-widest font-semibold mb-1",
                          shouldTrade ? "text-emerald-400" : "text-zinc-400"
                        )}>
                          {shouldTrade ? "Why Trade" : "Why Not Trade"}
                        </div>
                        <p className="text-xs text-foreground leading-relaxed">{event.trade_reason}</p>
                      </div>
                    )}

                    {/* Footer Meta */}
                    <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground flex-wrap">
                      <span>ID: {event.id}</span>
                      <span>Time: {event.triggered_time}</span>
                      <span>News IDs: {(event.news_ids || []).length}</span>
                      <span>Source: {event.gemini_source || "gemini"}</span>
                      {triggered && (
                        <Badge variant="outline" className="font-mono text-[8px] border-amber-500/30 text-amber-400 bg-amber-500/5">
                          Agent 2.5 → 3 Triggered
                        </Badge>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Footer */}
      <div className="font-mono text-[9px] text-muted-foreground opacity-25 text-center tracking-widest pb-1 border-t border-border/20 pt-3 mt-6">
        -- LIVE NEWS AGENT · INTRADAY MONITOR · AGENT 1+2 COMBINED --
      </div>
    </div>
  );
}
