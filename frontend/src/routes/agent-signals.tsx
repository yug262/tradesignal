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
} from "lucide-react";

export const Route = createFileRoute("/agent-signals")({
  component: AgentSignalsPage,
});

// ── Discovery Layer — Agent 1 ─────────────────────────────────────────────────
// This page shows the output of the Discovery layer.
// It does NOT show direction bias, gap expectations, or trade preferences.
// Those fields no longer exist in the Discovery schema.
// Agent 2 (market-open page) adds direction after validating the open.

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
  // New summary shape: watch, ignore, stale, strong, moderate, weak
  const summary = data?.signals_summary || {
    watch: 0, ignore: 0, stale: 0, strong: 0, moderate: 0, weak: 0,
  };

  // Filter by final_verdict (new Discovery schema)
  const filtered = signals.filter((s: any) => {
    const verdict = (s.reasoning?.final_verdict || "").toUpperCase();
    if (filter === "ALL") return true;
    if (filter === "IMPORTANT") return verdict === "IMPORTANT_EVENT";
    if (filter === "MODERATE") return verdict === "MODERATE_EVENT";
    if (filter === "MINOR") return verdict === "MINOR_EVENT";
    if (filter === "NOISE") return verdict === "NOISE";
    return true;
  });

  const confidenceColor = (conf: number) => {
    if (conf >= 80) return "text-emerald-400";
    if (conf >= 60) return "text-amber-400";
    if (conf >= 40) return "text-orange-400";
    return "text-red-400";
  };

  // Verdict badge — replaces old decision badge
  const verdictBadge = (verdict: string) => {
    const v = (verdict || "").toUpperCase();
    if (v === "IMPORTANT_EVENT")
      return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5"><CheckCircle2 size={10} className="mr-1" />IMPORTANT</Badge>;
    if (v === "MODERATE_EVENT")
      return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5"><Info size={10} className="mr-1" />MODERATE</Badge>;
    if (v === "MINOR_EVENT")
      return <Badge variant="outline" className="font-mono text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5"><Minus size={10} className="mr-1" />MINOR</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5"><XCircle size={10} className="mr-1" />NOISE</Badge>;
  };

  const strengthBadge = (strength: string) => {
    const s = (strength || "").toUpperCase();
    if (s === "STRONG") return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5">STRONG</Badge>;
    if (s === "MODERATE") return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5">MODERATE</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-border text-muted-foreground">WEAK</Badge>;
  };

  const freshnessBadge = (freshness: string) => {
    const f = (freshness || "").toUpperCase();
    if (f === "FRESH") return <span className="font-mono text-[9px] text-emerald-400">↻ FRESH</span>;
    if (f === "SLIGHTLY_OLD") return <span className="font-mono text-[9px] text-amber-400">↻ SLIGHTLY OLD</span>;
    if (f === "OLD") return <span className="font-mono text-[9px] text-zinc-400">↻ OLD</span>;
    return <span className="font-mono text-[9px] text-zinc-500">↻ REPEATED</span>;
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

      {/* Context note */}
      <div className="bg-primary/5 border border-primary/20 rounded-lg p-3">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong>Discovery Layer:</strong> Agent 1 reads recent news and explains what actually happened.
          It does <strong>not</strong> predict direction or give trade advice.
          Agent 2 (Market Open) validates the thesis against live data at 9:20 AM.
        </p>
      </div>

      {/* Summary Cards — aligned with new schema */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {[
          { label: "WATCH", count: summary.watch, icon: <Eye size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20", filterKey: "IMPORTANT" },
          { label: "IGNORE", count: summary.ignore, icon: <Minus size={16} />, color: "text-zinc-400", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "MINOR" },
          { label: "NOISE", count: summary.stale, icon: <XCircle size={16} />, color: "text-zinc-500", bg: "bg-zinc-500/5 border-zinc-500/20", filterKey: "NOISE" },
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

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest mr-1">Verdict:</span>
          {["ALL", "IMPORTANT", "MODERATE", "MINOR", "NOISE"].map((m) => (
            <Badge
              key={m} variant="outline"
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
            Click "Run Discovery Scan" to analyze overnight news
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const r = sig.reasoning || {};
            const snapshot = sig.stock_snapshot || {};
            const verdict = (r.final_verdict || "NOISE").toUpperCase();
            const isImportant = verdict === "IMPORTANT_EVENT";

            return (
              <div
                key={sig.id}
                className={cn(
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  !isImportant ? "opacity-70 border-border" : "border-border"
                )}
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Verdict */}
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                        <Newspaper size={14} className="text-muted-foreground" />
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                          {r.event_type?.replace("_", " ") || "other"} · {r.directness || "—"}
                        </div>
                      </div>
                      {verdictBadge(r.final_verdict)}
                      {strengthBadge(r.event_strength)}
                      {r.is_material && (
                        <Badge variant="outline" className="font-mono text-[9px] border-primary/30 text-primary bg-primary/5">
                          MATERIAL
                        </Badge>
                      )}
                    </div>

                    {/* Right: Confidence + Event Strength + Freshness */}
                    <div className="flex items-center gap-5">
                      <div className="text-center">
                        <div className={cn("text-lg font-bold font-mono tabular-nums", confidenceColor(sig.confidence || 0))}>
                          {sig.confidence || 0}%
                        </div>
                        <div className="font-mono text-[7px] text-muted-foreground uppercase tracking-widest">Confidence</div>
                      </div>
                      <div className="hidden sm:flex gap-4">
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">Freshness</div>
                          <div>{freshnessBadge(r.freshness)}</div>
                        </div>
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

                  {/* Event Summary (always visible) */}
                  {r.event_summary && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1">{r.event_summary}</p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    {/* Impact Analysis */}
                    {r.impact_analysis && (
                      <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                        <div className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold mb-1">Business Impact</div>
                        <p className="text-xs text-foreground leading-relaxed">{r.impact_analysis}</p>
                      </div>
                    )}

                    {/* Detailed Explanation */}
                    {r.detailed_explanation && (
                      <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                        <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold mb-1">Full Context</div>
                        <p className="text-xs text-muted-foreground leading-relaxed">{r.detailed_explanation}</p>
                      </div>
                    )}

                    {/* Positive Factors & Risks */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-border/30">
                      {r.key_positive_factors && r.key_positive_factors.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest mb-1 font-semibold">Positive Factors</div>
                          <ul className="space-y-0.5">
                            {r.key_positive_factors.map((c: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <CheckCircle2 size={9} className="text-emerald-400 mt-0.5 shrink-0" />
                                {c}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {r.key_risks && r.key_risks.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-red-400 uppercase tracking-widest mb-1 font-semibold">Risk Factors</div>
                          <ul className="space-y-0.5">
                            {r.key_risks.map((risk: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <ShieldAlert size={9} className="text-red-400 mt-0.5 shrink-0" />
                                {risk}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Reasoning Summary */}
                    {r.reasoning_summary && (
                      <div className="pt-2 border-t border-border/30">
                        <div className="bg-primary/5 border border-primary/20 rounded p-3">
                          <div className="font-mono text-[9px] text-primary uppercase tracking-widest mb-1 font-semibold">Reasoning</div>
                          <p className="text-xs text-foreground leading-relaxed">{r.reasoning_summary}</p>
                        </div>
                      </div>
                    )}

                    {/* Meta */}
                    <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground">
                      <span>Articles: <span className="text-foreground">{sig.news_article_ids?.length || 0}</span></span>
                      <span>Directness: <span className="text-foreground">{r.directness || "—"}</span></span>
                      <span>Freshness: <span className="text-foreground">{r.freshness || "—"}</span></span>
                      <span>Source: <span className="text-foreground">{r._source || "—"}</span></span>
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
        -- AGENT 1 · DISCOVERY LAYER · NEWS UNDERSTANDING ENGINE --
      </div>
    </div>
  );
}
