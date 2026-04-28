import React, { useEffect, useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api } from "@/backend";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import {
  Brain,
  Play,
  RefreshCw,
  Minus,
  Clock,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Newspaper,
  Eye,
  AlertTriangle,
  XCircle,
  CheckCircle2,
  Zap,
  TrendingUp,
  Target,
  FileText,
  Info,
} from "lucide-react";
import type { DiscoveryOutput } from "@/types/trading";

export const Route = createFileRoute("/agent-signals")({
  component: AgentSignalsPage,
});

// ── Discovery Layer — Agent 1 ─────────────────────────────────────────────────

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

  const signals = data?.signals || [];
  const summary = data?.signals_summary || {
    watch: 0, ignore: 0, stale: 0, strong: 0, moderate: 0, weak: 0,
  };

  // Filter logic
  const filtered = signals.filter((s: any) => {
    const isWatch = s.signal_type === "WATCH";
    if (filter === "ALL") return true;
    if (filter === "WATCH") return isWatch;
    if (filter === "IGNORE") return !isWatch;
    return true;
  });

  // ── Styling Helpers ────────────────────────────────────────────────────────

  const confidenceColor = (conf: string) => {
    const c = (conf || "LOW").toUpperCase();
    if (c === "HIGH") return "text-emerald-400";
    if (c === "MEDIUM") return "text-amber-400";
    return "text-zinc-500";
  };

  const biasBadge = (bias: string) => {
    const b = (bias || "NEUTRAL").toUpperCase();
    if (b === "BULLISH") return <Badge variant="outline" className="text-[10px] font-semibold border-emerald-500/30 text-emerald-400 bg-emerald-500/5 rounded-full px-2.5">BULLISH</Badge>;
    if (b === "BEARISH") return <Badge variant="outline" className="text-[10px] font-semibold border-rose-500/30 text-rose-400 bg-rose-500/5 rounded-full px-2.5">BEARISH</Badge>;
    if (b === "MIXED") return <Badge variant="outline" className="text-[10px] font-semibold border-amber-500/30 text-amber-400 bg-amber-500/5 rounded-full px-2.5">MIXED</Badge>;
    return <Badge variant="outline" className="text-[10px] font-semibold border-zinc-500/30 text-zinc-400 bg-zinc-500/5 rounded-full px-2.5">NEUTRAL</Badge>;
  };

  const verdictBadge = (isWatch: boolean, confidence: string) => {
    if (isWatch) {
      return (
        <Badge variant="outline" className="text-[10px] font-semibold border-emerald-500/30 text-emerald-400 bg-emerald-500/5 rounded-full px-2.5">
          <CheckCircle2 size={11} className="mr-1" />
          {confidence === "HIGH" ? "IMPORTANT" : "WATCH"}
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-[10px] font-semibold border-zinc-500/30 text-zinc-400 bg-zinc-500/5 rounded-full px-2.5">
        <XCircle size={11} className="mr-1" />
        NOISE
      </Badge>
    );
  };

  const confidenceBadge = (conf: string) => {
    const c = (conf || "LOW").toUpperCase();
    if (c === "HIGH") return <Badge variant="outline" className="text-[10px] font-semibold border-primary/30 text-primary bg-primary/5 rounded-full px-2.5">HIGH</Badge>;
    if (c === "MEDIUM") return <Badge variant="outline" className="text-[10px] font-semibold border-amber-500/30 text-amber-400 bg-amber-500/5 rounded-full px-2.5">MEDIUM</Badge>;
    return <Badge variant="outline" className="text-[10px] font-semibold border-border text-muted-foreground rounded-full px-2.5">LOW</Badge>;
  };

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto" data-ocid="agent-signals.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4 animate-fade-up">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-violet-500/15 text-violet-400">
              <Brain size={20} />
            </div>
            <div>
              <h2 className="font-display text-xl font-bold text-foreground tracking-tight">
                News Discovery
              </h2>
              <p className="text-[12px] text-muted-foreground">
                Agent 1 scans pre-market news at 8:30 AM and identifies tradeable events
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {status && (
            <Badge variant="outline" className="text-[11px] px-3 py-1 border-border text-muted-foreground rounded-full">
              <Clock size={11} className="mr-1.5" />
              Last: {status.last_run_time || "Never"}
            </Badge>
          )}
          <Button
            variant="outline" size="sm" onClick={loadSignals} disabled={loading}
            className="text-[12px] h-8 border-border rounded-lg"
          >
            <RefreshCw size={13} className={cn("mr-1.5", loading && "animate-spin")} />
            Refresh
          </Button>
          <Button
            size="sm" onClick={triggerRun} disabled={running}
            className="text-[12px] h-8 bg-violet-600 text-white hover:bg-violet-700 rounded-lg shadow-[0_0_15px_rgba(139,92,246,0.2)]"
          >
            {running ? (
              <><RefreshCw size={13} className="mr-1.5 animate-spin" /> Scanning...</>
            ) : (
              <><Play size={13} className="mr-1.5" /> Run Discovery</>
            )}
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 animate-fade-up stagger-1">
        {[
          { label: "Watch", count: summary.watch, icon: <Eye size={18} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20 hover:bg-emerald-500/10", filterKey: "WATCH" },
          { label: "Ignore", count: summary.ignore, icon: <Minus size={18} />, color: "text-zinc-400", bg: "bg-zinc-500/5 border-zinc-500/20 hover:bg-zinc-500/10", filterKey: "IGNORE" },
          { label: "Strong", count: summary.strong, icon: <Zap size={18} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20 hover:bg-red-500/10", filterKey: "ALL" },
          { label: "Moderate", count: summary.moderate, icon: <TrendingUp size={18} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20 hover:bg-amber-500/10", filterKey: "ALL" },
          { label: "Weak", count: summary.weak, icon: <Minus size={18} />, color: "text-zinc-500", bg: "bg-zinc-500/5 border-zinc-500/20 hover:bg-zinc-500/10", filterKey: "ALL" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn("border rounded-xl p-4 flex items-center gap-3 cursor-pointer transition-all duration-200 hover:scale-[1.02]", item.bg,
              filter === item.filterKey && filter !== "ALL" && "ring-2 ring-primary/30"
            )}
            onClick={() => setFilter(filter === item.filterKey ? "ALL" : item.filterKey)}
          >
            <div className={item.color}>{item.icon}</div>
            <div>
              <div className={cn("text-2xl font-bold font-mono tabular-nums", item.color)}>{item.count}</div>
              <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">{item.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Signal Cards */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-5 space-y-3">
              <div className="flex justify-between">
                <Skeleton className="h-6 w-32" />
                <Skeleton className="h-5 w-20" />
              </div>
              <Skeleton className="h-4 w-full" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-16 text-center space-y-4 animate-fade-up">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-secondary mx-auto">
            <Brain size={28} className="text-muted-foreground/30" />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">No assessments generated yet</p>
            <p className="text-xs text-muted-foreground mt-1">Run the Discovery scan to analyze today's pre-market news events.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3 animate-fade-up stagger-2">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const r = (sig.reasoning as DiscoveryOutput) || null;
            const cv = r?.combined_view || {};
            const rsn = cv?.reasoning || {};
            const snapshot = sig.stock_snapshot || {};
            const isWatch = sig.signal_type === "WATCH";

            return (
              <div
                key={sig.id}
                className={cn(
                  "bg-card border rounded-xl overflow-hidden transition-all",
                  !isWatch ? "opacity-60 border-border" : "border-border hover:border-primary/20"
                )}
              >
                {/* Main Row (Compact) */}
                <div
                  className="p-5 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "flex items-center justify-center w-10 h-10 rounded-lg border",
                        isWatch ? "bg-violet-500/10 border-violet-500/30" : "bg-secondary border-border"
                      )}>
                        <Newspaper size={18} className={isWatch ? "text-violet-400" : "text-muted-foreground"} />
                      </div>
                      <div>
                        <h3 className="font-bold text-base text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
                          {r?.news_analysis?.[0]?.event_type?.replace("_", " ") || "other"} · {cv?.final_confidence || "—"}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 ml-2">
                        {verdictBadge(isWatch, cv?.final_confidence)}
                        {biasBadge(cv?.final_bias)}
                        {confidenceBadge(cv?.final_confidence)}
                      </div>
                    </div>

                    <div className="flex items-center gap-5">
                      <div className="text-center">
                        <div className={cn("text-xl font-bold font-mono tabular-nums", confidenceColor(cv?.final_confidence))}>
                          {cv?.final_confidence === "HIGH" ? "80%" : (cv?.final_confidence === "MEDIUM" ? "55%" : "20%")}
                        </div>
                        <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Confidence</div>
                      </div>
                      <div className="hidden sm:block text-right">
                        <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Prev Close</div>
                        <div className="font-mono text-sm text-foreground tabular-nums">
                          {snapshot.last_close ? `₹${snapshot.last_close.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
                        </div>
                      </div>
                      <div className="text-muted-foreground">
                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                      </div>
                    </div>
                  </div>

                  {cv.executive_summary && (
                    <p className="text-xs text-muted-foreground mt-3 pl-[52px] leading-relaxed line-clamp-1 italic">
                      "{cv.executive_summary}"
                    </p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-5 space-y-4">
                    {/* Conflict Alert */}
                    {cv.conflict_detected && (
                      <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-3">
                        <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" />
                        <div className="space-y-1">
                          <p className="text-[11px] font-bold text-amber-500 uppercase tracking-wider">Conflict Detected</p>
                          <p className="text-sm text-muted-foreground leading-relaxed">{cv.conflict_reason}</p>
                        </div>
                      </div>
                    )}

                    {/* Main Content Area */}
                    <Tabs defaultValue="thesis" className="w-full">
                      <TabsList className="bg-background/50 h-9 p-1 rounded-lg">
                        <TabsTrigger value="thesis" className="text-[11px] uppercase h-7 rounded-md">Combined Thesis</TabsTrigger>
                        <TabsTrigger value="articles" className="text-[11px] uppercase h-7 rounded-md">News Breakdown ({r.news_analysis?.length || 0})</TabsTrigger>
                      </TabsList>

                      <TabsContent value="thesis" className="pt-4 space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div className="space-y-3">
                            <DetailBlock title="Main Driver" value={rsn?.main_driver} icon={<Zap size={12} className="text-primary" />} />
                            <DetailBlock title="Trading Thesis" value={cv?.combined_trading_thesis} icon={<Target size={12} />} />
                            <DetailBlock title="Invalidation" value={cv?.combined_invalidation} icon={<ShieldAlert size={12} className="text-rose-500" />} />
                          </div>
                          <div className="space-y-3">
                            <ListBlock title="Supporting Points" items={rsn?.supporting_points} />
                            <ListBlock title="Key Risks" items={cv?.key_risks} />
                            <div className="p-4 rounded-xl bg-background/50 border border-border/50">
                              <h4 className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">Confidence Reason</h4>
                              <p className="text-sm text-muted-foreground italic leading-relaxed">"{rsn?.confidence_reason}"</p>
                            </div>
                          </div>
                        </div>

                        {/* Validation Section */}
                        <div className="p-4 rounded-xl bg-primary/5 border border-primary/20">
                          <h4 className="text-[11px] uppercase tracking-wider text-primary font-semibold mb-3">
                            <Info size={12} className="inline mr-1.5 mb-0.5" />
                            What Agent 2 Should Validate
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {rsn?.what_agent_2_should_validate?.map((v: string, i: number) => (
                              <Badge key={i} variant="secondary" className="text-[11px] bg-background border-border/50 font-normal rounded-lg px-3 py-1">
                                {v}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="articles" className="pt-4 space-y-3">
                        {r.news_analysis?.map((na, i) => (
                          <div key={i} className="p-4 rounded-xl border border-border/50 bg-background/30 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                <FileText size={12} /> Article #{na.news_number} · {na.event_type}
                              </span>
                              <Badge variant="outline" className="text-[10px] h-5 rounded-full px-2.5">{na.importance} IMPORTANCE</Badge>
                            </div>
                            <p className="text-sm font-semibold text-foreground">{na.what_happened}</p>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <ListBlock title="Confirmed Facts" items={na.confirmed_facts} compact />
                              <ListBlock title="Unknowns" items={na.unknowns} compact />
                            </div>
                          </div>
                        ))}
                      </TabsContent>
                    </Tabs>

                    {/* Footer Meta */}
                    <div className="flex items-center gap-4 pt-3 border-t border-border/30 text-[11px] font-mono text-muted-foreground/60">
                      <span>Articles: {sig.news_article_ids?.length || 0}</span>
                      <span>Source: {r._source || "gemini"}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function DetailBlock({ title, value, icon }: { title: string; value?: string; icon?: React.ReactNode }) {
  return (
    <div className="space-y-1.5 bg-background/50 p-4 rounded-xl border border-border/50">
      <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold flex items-center gap-1.5">
        {icon} {title}
      </div>
      <p className="text-sm text-foreground leading-relaxed">{value || "—"}</p>
    </div>
  );
}

function ListBlock({ title, items, compact }: { title: string; items?: string[]; compact?: boolean }) {
  if (!items || items.length === 0) return null;
  return (
    <div className={cn("space-y-2", !compact && "bg-background/50 p-4 rounded-xl border border-border/50")}>
      <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">{title}</div>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-[12px] text-muted-foreground flex items-start gap-2 leading-relaxed">
            <span className="text-primary mt-0.5 shrink-0">•</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
