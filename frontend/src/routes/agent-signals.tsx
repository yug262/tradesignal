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
  Info,
  Target,
  FileText,
  HelpCircle,
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
    if (b === "BULLISH") return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5">BULLISH</Badge>;
    if (b === "BEARISH") return <Badge variant="outline" className="font-mono text-[9px] border-rose-500/30 text-rose-400 bg-rose-500/5">BEARISH</Badge>;
    if (b === "MIXED") return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5">MIXED</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5">NEUTRAL</Badge>;
  };

  const verdictBadge = (isWatch: boolean, confidence: string) => {
    if (isWatch) {
      return (
        <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5">
          <CheckCircle2 size={10} className="mr-1" />
          {confidence === "HIGH" ? "IMPORTANT" : "WATCH"}
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5">
        <XCircle size={10} className="mr-1" />
        NOISE
      </Badge>
    );
  };

  const confidenceBadge = (conf: string) => {
    const c = (conf || "LOW").toUpperCase();
    if (c === "HIGH") return <Badge variant="outline" className="font-mono text-[9px] border-primary/30 text-primary bg-primary/5">HIGH CONF</Badge>;
    if (c === "MEDIUM") return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5">MEDIUM CONF</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground">LOW CONF</Badge>;
  };

  return (
    <div className="p-5 space-y-5" data-ocid="agent-signals.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-primary" />
          <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
            Agent 1 · Discovery Layer
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
            variant="outline" size="sm" onClick={loadSignals} disabled={loading}
            className="font-mono text-[10px] h-6 border-border"
          >
            <RefreshCw size={10} className={`mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button
            size="sm" onClick={triggerRun} disabled={running}
            className="font-mono text-[10px] h-6 bg-primary text-primary-foreground hover:bg-primary/80"
          >
            {running ? (
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Scanning...</>
            ) : (
              <><Play size={10} className="mr-1" /> Run Discovery Scan</>
            )}
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {[
          { label: "WATCH", count: summary.watch, icon: <Eye size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20", filterKey: "WATCH" },
          { label: "IGNORE", count: summary.ignore, icon: <Minus size={16} />, color: "text-zinc-400", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "IGNORE" },
          { label: "STRONG ⚡", count: summary.strong, icon: <Zap size={16} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20", filterKey: "ALL" },
          { label: "MODERATE", count: summary.moderate, icon: <TrendingUp size={16} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20", filterKey: "ALL" },
          { label: "WEAK", count: summary.weak, icon: <Minus size={16} />, color: "text-zinc-500", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "ALL" },
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
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-lg p-12 text-center space-y-3">
          <Brain size={32} className="mx-auto text-muted-foreground opacity-20" />
          <p className="font-mono text-xs text-muted-foreground">No assessments generated yet</p>
        </div>
      ) : (
        <div className="space-y-3">
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
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  !isWatch ? "opacity-70 border-border" : "border-border"
                )}
              >
                {/* Main Row (Compact) */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                        <Newspaper size={14} className="text-muted-foreground" />
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                          {r?.news_analysis?.[0]?.event_type?.replace("_", " ") || "other"} · {cv?.final_confidence || "—"}
                        </div>
                      </div>
                      {verdictBadge(isWatch, cv?.final_confidence)}
                      {biasBadge(cv?.final_bias)}
                      {confidenceBadge(cv?.final_confidence)}
                    </div>

                    <div className="flex items-center gap-5">
                      <div className="text-center">
                        <div className={cn("text-lg font-bold font-mono tabular-nums", confidenceColor(cv?.final_confidence))}>
                          {cv?.final_confidence === "HIGH" ? "80%" : (cv?.final_confidence === "MEDIUM" ? "55%" : "20%")}
                        </div>
                        <div className="font-mono text-[7px] text-muted-foreground uppercase tracking-widest">Confidence</div>
                      </div>
                      <div className="hidden sm:flex gap-4">
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">Prev Close</div>
                          <div className="font-mono text-xs text-foreground tabular-nums">
                            {snapshot.last_close ? snapshot.last_close.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
                          </div>
                        </div>
                      </div>
                      <div className="text-muted-foreground">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </div>
                    </div>
                  </div>

                  {cv.executive_summary && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1 italic">
                      "{cv.executive_summary}"
                    </p>
                  )}
                </div>

                {/* Expanded Details (Enhanced with all new fields) */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    {/* Conflict Alert */}
                    {cv.conflict_detected && (
                      <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-start gap-3">
                        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                        <div className="space-y-1">
                          <p className="text-[10px] font-bold text-amber-600 uppercase tracking-widest">Conflict Detected</p>
                          <p className="text-xs text-muted-foreground leading-relaxed">{cv.conflict_reason}</p>
                        </div>
                      </div>
                    )}

                    {/* Main Content Area */}
                    <Tabs defaultValue="thesis" className="w-full">
                      <TabsList className="bg-background/50 h-8 p-1">
                        <TabsTrigger value="thesis" className="text-[10px] uppercase h-6">Combined Thesis</TabsTrigger>
                        <TabsTrigger value="articles" className="text-[10px] uppercase h-6">News Breakdown ({r.news_analysis?.length || 0})</TabsTrigger>
                      </TabsList>

                      <TabsContent value="thesis" className="pt-4 space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <div className="space-y-4">
                            <DetailBlock title="Main Driver" value={rsn?.main_driver} icon={<Zap size={10} className="text-primary" />} />
                            <DetailBlock title="Trading Thesis" value={cv?.combined_trading_thesis} icon={<Target size={10} />} />
                            <DetailBlock title="Invalidation" value={cv?.combined_invalidation} icon={<ShieldAlert size={10} className="text-rose-500" />} />
                          </div>
                          <div className="space-y-4">
                            <ListBlock title="Supporting Points" items={rsn?.supporting_points} />
                            <ListBlock title="Key Risks" items={cv?.key_risks} />
                            <div className="p-3 rounded bg-background/50 border border-border/50">
                              <h4 className="text-[9px] uppercase tracking-widest text-muted-foreground font-bold mb-1">Confidence Reason</h4>
                              <p className="text-xs text-muted-foreground italic">"{rsn?.confidence_reason}"</p>
                            </div>
                          </div>
                        </div>

                        {/* Validation Section */}
                        <div className="p-3 rounded bg-primary/5 border border-primary/20">
                          <h4 className="text-[9px] uppercase tracking-widest text-primary font-bold mb-2">Agent 2 Validation Directives</h4>
                          <div className="flex flex-wrap gap-2">
                            {rsn?.what_agent_2_should_validate?.map((v: string, i: number) => (
                              <Badge key={i} variant="secondary" className="text-[9px] bg-background border-border/50 font-normal">
                                {v}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="articles" className="pt-4 space-y-3">
                        {r.news_analysis?.map((na, i) => (
                          <div key={i} className="p-3 rounded border border-border/50 bg-background/30 space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1">
                                <FileText size={10} /> Article #{na.news_number} · {na.event_type}
                              </span>
                              <Badge variant="outline" className="text-[8px] h-4">{na.importance} IMPORTANCE</Badge>
                            </div>
                            <p className="text-xs font-semibold">{na.what_happened}</p>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <ListBlock title="Confirmed Facts" items={na.confirmed_facts} compact />
                              <ListBlock title="Unknowns" items={na.unknowns} compact />
                            </div>
                          </div>
                        ))}
                      </TabsContent>
                    </Tabs>

                    {/* Footer Meta */}
                    <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground opacity-50">
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
    <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
      <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold flex items-center gap-1.5">
        {icon} {title}
      </div>
      <p className="text-xs text-foreground leading-relaxed">{value || "—"}</p>
    </div>
  );
}

function ListBlock({ title, items, compact }: { title: string; items?: string[]; compact?: boolean }) {
  if (!items || items.length === 0) return null;
  return (
    <div className={cn("space-y-1.5", !compact && "bg-background/50 p-3 rounded border border-border/50")}>
      <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">{title}</div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
            <span className="text-primary mt-0.5">•</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
