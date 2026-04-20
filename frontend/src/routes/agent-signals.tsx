import { useEffect, useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api } from "@/backend";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Brain,
  Play,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  Ban,
  Clock,
  Target,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Zap,
  BarChart3,
  Newspaper,
  Eye,
  AlertTriangle,
  XCircle,
  ArrowUpCircle,
  ArrowDownCircle,
} from "lucide-react";

export const Route = createFileRoute("/agent-signals")({
  component: AgentSignalsPage,
});

function AgentSignalsPage() {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [filter, setFilter] = useState<string>("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadSignals = useCallback(async () => {
    setLoading(true);
    try {
      const [signals, agentStatus] = await Promise.all([
        api.getAgentSignals(),
        api.getAgentStatus(),
      ]);
      setData(signals);
      setStatus(agentStatus);
    } catch (err) {
      console.error("Failed to load signals", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSignals();
  }, [loadSignals]);

  const triggerRun = async () => {
    setRunning(true);
    try {
      await api.triggerAgentRun();
      await loadSignals();
    } catch (err) {
      console.error("Agent run failed", err);
    } finally {
      setRunning(false);
    }
  };

  const formatNumber = (val: number | null) => {
    if (val === null || val === undefined) return "—";
    return val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const signals = data?.signals || [];
  const summary = data?.signals_summary || { watch: 0, ignore: 0, stale: 0, high: 0, medium: 0, low: 0 };

  const filtered = signals.filter((s: any) => {
    const r = s.reasoning || {};
    const decision = (r.decision || "").toUpperCase();
    if (filter === "ALL") return true;
    if (filter === "WATCH") return decision.includes("WATCH");
    if (filter === "IGNORE") return decision === "IGNORE";
    if (filter === "STALE") return decision.includes("STALE");
    return true;
  });

  const confidenceColor = (conf: number) => {
    if (conf >= 0.8) return "text-emerald-400";
    if (conf >= 0.6) return "text-amber-400";
    if (conf >= 0.4) return "text-orange-400";
    return "text-red-400";
  };

  const decisionBadge = (decision: string) => {
    const d = (decision || "").toUpperCase();
    if (d.includes("WATCH BOTH")) return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5"><Eye size={10} className="mr-1"/> WATCH BOTH</Badge>;
    if (d.includes("WATCH INTRADAY")) return <Badge variant="outline" className="font-mono text-[9px] border-sky-500/30 text-sky-400 bg-sky-500/5"><Eye size={10} className="mr-1"/> WATCH INTRADAY</Badge>;
    if (d.includes("WATCH DELIVERY")) return <Badge variant="outline" className="font-mono text-[9px] border-violet-500/30 text-violet-400 bg-violet-500/5"><Eye size={10} className="mr-1"/> WATCH DELIVERY</Badge>;
    if (d.includes("STALE")) return <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5"><XCircle size={10} className="mr-1"/> STALE</Badge>;
    if (d === "IGNORE") return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5"><Ban size={10} className="mr-1"/> IGNORE</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground">{decision}</Badge>;
  };

  const directionIcon = (dir: string) => {
    const d = (dir || "").toUpperCase();
    if (d === "BULLISH") return <ArrowUpCircle size={14} className="text-emerald-400" />;
    if (d === "BEARISH") return <ArrowDownCircle size={14} className="text-red-400" />;
    return <Minus size={14} className="text-zinc-400" />;
  };

  const directionColor = (dir: string) => {
    const d = (dir || "").toUpperCase();
    if (d === "BULLISH") return "text-emerald-400";
    if (d === "BEARISH") return "text-red-400";
    return "text-zinc-400";
  };

  const priorityBadge = (priority: string) => {
    const p = (priority || "").toUpperCase();
    if (p === "HIGH") return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5">HIGH</Badge>;
    if (p === "MEDIUM") return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5">MED</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground">LOW</Badge>;
  };

  const gapBadge = (gap: string) => {
    const g = (gap || "").toUpperCase();
    if (g.includes("GAP UP")) return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5"><TrendingUp size={10} className="mr-1"/>GAP UP</Badge>;
    if (g.includes("GAP DOWN")) return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5"><TrendingDown size={10} className="mr-1"/>GAP DOWN</Badge>;
    if (g.includes("FLAT")) return <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5"><Minus size={10} className="mr-1"/>FLAT</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground">UNCLEAR</Badge>;
  };

  return (
    <div className="p-5 space-y-5" data-ocid="agent-signals.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-primary" />
          <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
            Agent 1 · Pre-Market Intelligence
          </span>
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 h-4 border-primary/30 text-primary bg-primary/5">
            8:30 AM
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {status && (
            <Badge variant="outline" className="font-mono text-[9px] px-2 py-0.5 border-border text-muted-foreground">
              <Clock size={8} className="mr-1" />
              Last: {status.last_run_time || "Never"}
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={loadSignals}
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
            className="font-mono text-[10px] h-6 bg-primary text-primary-foreground hover:bg-primary/80"
          >
            {running ? (
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Scanning...</>
            ) : (
              <><Play size={10} className="mr-1" /> Run Pre-Market Scan</>
            )}
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {[
          { label: "WATCH", count: summary.watch, icon: <Eye size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20", filterKey: "WATCH" },
          { label: "IGNORE", count: summary.ignore, icon: <Ban size={16} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20", filterKey: "IGNORE" },
          { label: "STALE", count: summary.stale, icon: <XCircle size={16} />, color: "text-zinc-500", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "STALE" },
          { label: "HIGH ⚡", count: summary.high, icon: <Zap size={16} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20", filterKey: "ALL" },
          { label: "MEDIUM", count: summary.medium, icon: <Minus size={16} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20", filterKey: "ALL" },
          { label: "LOW", count: summary.low, icon: <Minus size={16} />, color: "text-zinc-500", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "ALL" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn("border rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-all hover:scale-[1.02]", item.bg)}
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

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest mr-1">Decision:</span>
          {["ALL", "WATCH", "IGNORE", "STALE"].map((m) => (
            <Badge
              key={m}
              variant="outline"
              className={cn(
                "font-mono text-[9px] px-2 py-0.5 cursor-pointer transition-all",
                filter === m
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/30"
              )}
              onClick={() => setFilter(m)}
            >
              {m}
            </Badge>
          ))}
        </div>

        <span className="font-mono text-[9px] text-muted-foreground ml-auto">
          Showing {filtered.length} of {signals.length} assessments
        </span>
      </div>

      {/* Signal Cards */}
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
          <Brain size={32} className="mx-auto text-muted-foreground opacity-20" />
          <p className="font-mono text-xs text-muted-foreground">No assessments generated yet</p>
          <p className="font-mono text-[10px] text-muted-foreground opacity-50">
            Click "Run Pre-Market Scan" to analyze overnight news
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const r = sig.reasoning || {};
            const snapshot = sig.stock_snapshot || {};
            const decision = r.decision || "IGNORE";
            const isWatch = decision.toUpperCase().includes("WATCH");

            return (
              <div
                key={sig.id}
                className={cn(
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  !isWatch ? "opacity-60 border-border" : "border-border"
                )}
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Direction + Decision */}
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                        {directionIcon(r.direction_bias)}
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className={cn("font-mono text-[9px] uppercase tracking-widest font-bold", directionColor(r.direction_bias))}>
                          {r.direction_bias || "NEUTRAL"}
                        </div>
                      </div>
                      {decisionBadge(decision)}
                      {priorityBadge(r.priority)}
                      {gapBadge(r.gap_expectation)}
                    </div>

                    {/* Right: Confidence + Key Metrics */}
                    <div className="flex items-center gap-5">
                      <div className="text-center">
                        <div className={cn("text-lg font-bold font-mono tabular-nums", confidenceColor(sig.confidence || 0))}>
                          {Math.round((sig.confidence || 0) * 100)}%
                        </div>
                        <div className="font-mono text-[7px] text-muted-foreground uppercase tracking-widest">Confidence</div>
                      </div>

                      <div className="hidden sm:flex gap-4">
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">Prev Close</div>
                          <div className="font-mono text-xs text-foreground tabular-nums">{formatNumber(snapshot.previous_close || snapshot.last_close)}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">Trend</div>
                          <div className={cn("font-mono text-xs capitalize",
                            snapshot.recent_trend === "up" ? "text-emerald-400" :
                            snapshot.recent_trend === "down" ? "text-red-400" : "text-muted-foreground"
                          )}>{snapshot.recent_trend || "—"}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">Event</div>
                          <div className={cn("font-mono text-xs",
                            r.event_strength === "STRONG" ? "text-emerald-400" :
                            r.event_strength === "MODERATE" ? "text-amber-400" : "text-zinc-500"
                          )}>{r.event_strength || "—"}</div>
                        </div>
                      </div>

                      <div className="text-muted-foreground">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </div>
                    </div>
                  </div>

                  {/* Event Summary (always visible) */}
                  {r.event_summary && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1">{r.event_summary}</p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    {/* Top: Market Context Grid */}
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 pb-4 border-b border-border/30">
                      <div className="bg-background/50 rounded p-2 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Prev Close</div>
                        <div className="font-mono text-xs text-foreground tabular-nums">{formatNumber(snapshot.previous_close || snapshot.last_close)}</div>
                      </div>
                      <div className="bg-background/50 rounded p-2 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">5d Change</div>
                        <div className={cn("font-mono text-xs tabular-nums", (snapshot.change_5d_percent || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                          {snapshot.change_5d_percent != null ? `${snapshot.change_5d_percent}%` : "—"}
                        </div>
                      </div>
                      <div className="bg-background/50 rounded p-2 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">20d Change</div>
                        <div className={cn("font-mono text-xs tabular-nums", (snapshot.change_20d_percent || 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                          {snapshot.change_20d_percent != null ? `${snapshot.change_20d_percent}%` : "—"}
                        </div>
                      </div>
                      <div className="bg-background/50 rounded p-2 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Avg Vol (5d)</div>
                        <div className="font-mono text-xs text-foreground tabular-nums">{(snapshot.avg_volume_5d || 0).toLocaleString()}</div>
                      </div>
                      <div className="bg-background/50 rounded p-2 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">52W High</div>
                        <div className="font-mono text-xs text-foreground tabular-nums">{formatNumber(snapshot["52_week_high"])}</div>
                      </div>
                      <div className="bg-background/50 rounded p-2 border border-border/50">
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">52W Low</div>
                        <div className="font-mono text-xs text-foreground tabular-nums">{formatNumber(snapshot["52_week_low"])}</div>
                      </div>
                    </div>

                    {/* Intelligence Sections */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {r.why_it_matters && (
                        <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                          <div className="flex items-center gap-1">
                            <Target size={10} className="text-primary" />
                            <span className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold">Why It Matters</span>
                          </div>
                          <p className="text-xs text-foreground leading-relaxed">{r.why_it_matters}</p>
                        </div>
                      )}
                      {r.open_expectation && (
                        <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                          <div className="flex items-center gap-1">
                            <BarChart3 size={10} className="text-primary" />
                            <span className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold">Open Expectation</span>
                          </div>
                          <p className="text-xs text-foreground leading-relaxed">{r.open_expectation}</p>
                        </div>
                      )}
                    </div>

                    {/* Key Drivers & Risks */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-border/30">
                      {r.key_drivers && r.key_drivers.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest mb-1 font-semibold">Key Drivers</div>
                          <ul className="space-y-0.5">
                            {r.key_drivers.map((c: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <TrendingUp size={9} className="text-emerald-400 mt-0.5 shrink-0" />
                                {c}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {r.risks && r.risks.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-red-400 uppercase tracking-widest mb-1 font-semibold">Risk Factors</div>
                          <ul className="space-y-0.5">
                            {r.risks.map((risk: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <ShieldAlert size={9} className="text-red-400 mt-0.5 shrink-0" />
                                {risk}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Confirmation Needed & Invalid If */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-border/30">
                      {r.open_confirmation_needed && r.open_confirmation_needed.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-blue-400 uppercase tracking-widest mb-1 font-semibold">Confirm At Open</div>
                          <ul className="space-y-0.5">
                            {r.open_confirmation_needed.map((c: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <Eye size={9} className="text-blue-400 mt-0.5 shrink-0" />
                                {c}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {r.invalid_if && r.invalid_if.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-orange-400 uppercase tracking-widest mb-1 font-semibold">Invalid If</div>
                          <ul className="space-y-0.5">
                            {r.invalid_if.map((c: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <AlertTriangle size={9} className="text-orange-400 mt-0.5 shrink-0" />
                                {c}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Final Summary */}
                    {r.final_summary && (
                      <div className="pt-2 border-t border-border/30">
                        <div className="bg-primary/5 border border-primary/20 rounded p-3">
                          <div className="font-mono text-[9px] text-primary uppercase tracking-widest mb-1 font-semibold">Final Summary</div>
                          <p className="text-xs text-foreground leading-relaxed">{r.final_summary}</p>
                        </div>
                      </div>
                    )}

                    {/* Meta */}
                    <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground">
                      <span>Articles: <span className="text-foreground">{sig.news_article_ids?.length || 0}</span></span>
                      <span>Directness: <span className="text-foreground">{r.directness || "N/A"}</span></span>
                      <span>Trend: <span className="text-foreground">{snapshot.recent_trend || "N/A"}</span></span>
                      <span>20d from high: <span className="text-foreground">{snapshot.distance_from_20d_high_percent != null ? `${snapshot.distance_from_20d_high_percent}%` : "N/A"}</span></span>
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
        -- AGENT 1 . GEMINI INTELLIGENCE . PRE-MARKET WATCHLIST ENGINE --
      </div>
    </div>
  );
}
