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
  CheckCircle2,
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
  const [modeFilter, setModeFilter] = useState<string>("ALL");
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
  const summary = data?.signals_summary || { buy: 0, sell: 0, hold: 0, no_trade: 0 };

  const filtered = signals.filter((s: any) => {
    if (filter !== "ALL" && s.signal_type !== filter) return false;
    if (modeFilter !== "ALL" && s.trade_mode !== modeFilter) return false;
    return true;
  });

  const signalIcon = (type: string) => {
    switch (type) {
      case "BUY": return <TrendingUp size={14} />;
      case "SELL": return <TrendingDown size={14} />;
      case "HOLD": return <Minus size={14} />;
      default: return <Ban size={14} />;
    }
  };

  const signalColor = (type: string) => {
    switch (type) {
      case "BUY": return "text-emerald-400 border-emerald-500/30 bg-emerald-500/10";
      case "SELL": return "text-red-400 border-red-500/30 bg-red-500/10";
      case "HOLD": return "text-amber-400 border-amber-500/30 bg-amber-500/10";
      default: return "text-zinc-500 border-zinc-500/30 bg-zinc-500/10";
    }
  };

  const confidenceColor = (conf: number) => {
    if (conf >= 0.8) return "text-emerald-400";
    if (conf >= 0.6) return "text-amber-400";
    if (conf >= 0.4) return "text-orange-400";
    return "text-red-400";
  };

  return (
    <div className="p-5 space-y-5" data-ocid="agent-signals.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-primary" />
          <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
            Gemini Trading Agent · Pre-Market Intelligence
          </span>
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
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Running...</>
            ) : (
              <><Play size={10} className="mr-1" /> Run Agent</>
            )}
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "BUY", count: summary.buy, icon: <TrendingUp size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20" },
          { label: "SELL", count: summary.sell, icon: <TrendingDown size={16} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20" },
          { label: "HOLD", count: summary.hold, icon: <Minus size={16} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20" },
          { label: "NO TRADE", count: summary.no_trade, icon: <Ban size={16} />, color: "text-zinc-500", bg: "bg-zinc-500/5 border-zinc-500/20" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn("border rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-all hover:scale-[1.02]", item.bg)}
            onClick={() => setFilter(filter === item.label.replace(" ", "_") ? "ALL" : item.label.replace(" ", "_"))}
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
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest mr-1">Mode:</span>
        {["ALL", "INTRADAY", "DELIVERY"].map((m) => (
          <Badge
            key={m}
            variant="outline"
            className={cn(
              "font-mono text-[9px] px-2 py-0.5 cursor-pointer transition-all",
              modeFilter === m
                ? "bg-primary/10 border-primary/30 text-primary"
                : "border-border text-muted-foreground hover:border-primary/30"
            )}
            onClick={() => setModeFilter(m)}
          >
            {m}
          </Badge>
        ))}
        <span className="font-mono text-[9px] text-muted-foreground ml-2">
          Showing {filtered.length} of {signals.length} signals
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
          <p className="font-mono text-xs text-muted-foreground">No signals generated yet</p>
          <p className="font-mono text-[10px] text-muted-foreground opacity-50">
            Click "Run Agent" to trigger a pre-market analysis
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const reasoning = sig.reasoning || {};
            const snapshot = sig.stock_snapshot || {};

            return (
              <div
                key={sig.id}
                className="bg-card border border-border rounded-lg overflow-hidden transition-all"
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Signal */}
                    <div className="flex items-center gap-3">
                      <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-mono text-xs font-bold", signalColor(sig.signal_type))}>
                        {signalIcon(sig.signal_type)}
                        {sig.signal_type}
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">NSE</div>
                      </div>
                      <Badge
                        variant="outline"
                        className={cn(
                          "font-mono text-[9px] px-1.5 py-0 h-4",
                          sig.trade_mode === "INTRADAY"
                            ? "border-sky-500/30 text-sky-400 bg-sky-500/5"
                            : "border-violet-500/30 text-violet-400 bg-violet-500/5"
                        )}
                      >
                        {sig.trade_mode}
                      </Badge>
                    </div>

                    {/* Right: Score + Levels */}
                    <div className="flex items-center gap-5">
                      {/* Confidence Gauge */}
                      <div className="text-center">
                        <div className={cn("text-lg font-bold font-mono tabular-nums", confidenceColor(sig.confidence || 0))}>
                          {Math.round((sig.confidence || 0) * 100)}%
                        </div>
                        <div className="font-mono text-[7px] text-muted-foreground uppercase tracking-widest">Confidence</div>
                      </div>

                      {/* Entry / SL / Target */}
                      <div className="hidden sm:flex gap-4">
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">Entry</div>
                          <div className="font-mono text-xs text-foreground tabular-nums">{formatNumber(sig.entry_price)}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-red-400 uppercase tracking-widest">SL</div>
                          <div className="font-mono text-xs text-red-400 tabular-nums">{formatNumber(sig.stop_loss)}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-emerald-400 uppercase tracking-widest">Target</div>
                          <div className="font-mono text-xs text-emerald-400 tabular-nums">{formatNumber(sig.target_price)}</div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest">R:R</div>
                          <div className="font-mono text-xs text-foreground tabular-nums">{sig.risk_reward}x</div>
                        </div>
                      </div>

                      <div className="text-muted-foreground">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </div>
                    </div>
                  </div>


                </div>

                {/* Expanded Reasoning */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    {/* Mobile: Entry/SL/Target */}
                    <div className="sm:hidden grid grid-cols-4 gap-2">
                      <div>
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Entry</div>
                        <div className="font-mono text-xs text-foreground tabular-nums">{formatNumber(sig.entry_price)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-red-400 uppercase">SL</div>
                        <div className="font-mono text-xs text-red-400 tabular-nums">{formatNumber(sig.stop_loss)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-emerald-400 uppercase">Target</div>
                        <div className="font-mono text-xs text-emerald-400 tabular-nums">{formatNumber(sig.target_price)}</div>
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">R:R</div>
                        <div className="font-mono text-xs text-foreground tabular-nums">{sig.risk_reward}x</div>
                      </div>
                    </div>

                    {/* Reasoning Sections */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {reasoning.news_analysis && (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1">
                            <Newspaper size={10} className="text-primary" />
                            <span className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold">News Analysis</span>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">{reasoning.news_analysis}</p>
                        </div>
                      )}
                      {reasoning.price_analysis && (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1">
                            <BarChart3 size={10} className="text-primary" />
                            <span className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold">Price Analysis</span>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">{reasoning.price_analysis}</p>
                        </div>
                      )}
                      {reasoning.why_tradable && (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1">
                            <Target size={10} className="text-primary" />
                            <span className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold">Tradability</span>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">{reasoning.why_tradable}</p>
                        </div>
                      )}
                      {reasoning.trade_mode_rationale && (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1">
                            <Zap size={10} className="text-primary" />
                            <span className="font-mono text-[9px] text-primary uppercase tracking-widest font-semibold">Trade Mode</span>
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">{reasoning.trade_mode_rationale}</p>
                        </div>
                      )}
                    </div>

                    {/* Catalysts & Risks */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-border/30">
                      {reasoning.key_catalysts && reasoning.key_catalysts.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest mb-1 font-semibold">Key Catalysts</div>
                          <ul className="space-y-0.5">
                            {reasoning.key_catalysts.map((c: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <TrendingUp size={9} className="text-emerald-400 mt-0.5 shrink-0" />
                                {c}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {reasoning.risk_factors && reasoning.risk_factors.length > 0 && (
                        <div>
                          <div className="font-mono text-[9px] text-red-400 uppercase tracking-widest mb-1 font-semibold">Risk Factors</div>
                          <ul className="space-y-0.5">
                            {reasoning.risk_factors.map((r: string, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                <ShieldAlert size={9} className="text-red-400 mt-0.5 shrink-0" />
                                {r}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground">
                      <span>Articles: <span className="text-foreground">{sig.news_article_ids?.length || 0}</span></span>
                      <span>Prev Close: <span className="text-foreground">{formatNumber(snapshot.last_close)}</span></span>
                      <span>Volume: <span className="text-foreground">{(snapshot.current_volume || 0).toLocaleString()}</span></span>
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
        -- AGENT SIGNALS . GEMINI POWERED . PRE-MARKET INTELLIGENCE ENGINE --
      </div>
    </div>
  );
}
