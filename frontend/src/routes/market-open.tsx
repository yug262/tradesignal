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
  Target,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  Ban,
  Activity,
  Eye,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowUpCircle,
  ArrowDownCircle,
  Zap,
  Info,
  XCircle,
} from "lucide-react";

export const Route = createFileRoute("/market-open")({
  component: MarketOpenPage,
});

function MarketOpenPage() {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [runningConfirm, setRunningConfirm] = useState(false);
  const [confFilter, setConfFilter] = useState<string>("ALL");
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

  const triggerConfirm = async () => {
    setRunningConfirm(true);
    try {
      await api.triggerConfirmationRun();
      await loadSignals();
    } catch (err) {
      console.error("Agent confirm run failed", err);
    } finally {
      setRunningConfirm(false);
    }
  };

  const signals = data?.signals || [];
  const summary = data?.confirmation_summary || { pending: 0, confirmed: 0, revised: 0, invalidated: 0 };

  const filtered = signals.filter((s: any) => {
    if (confFilter !== "ALL" && s.confirmation_status !== confFilter.toLowerCase()) return false;
    return true;
  });

  const confidenceColor = (conf: string) => {
    const c = (conf || "").toUpperCase();
    if (c === "HIGH") return "text-emerald-400";
    if (c === "MEDIUM") return "text-amber-400";
    return "text-zinc-500";
  };

  const confirmationBadge = (status: string) => {
    switch (status) {
      case "confirmed": return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5"><CheckCircle2 size={10} className="mr-1"/> CONFIRMED</Badge>;
      case "revised": return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5"><RefreshCw size={10} className="mr-1"/> REVISED</Badge>;
      case "invalidated": return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5"><Ban size={10} className="mr-1"/> INVALIDATED</Badge>;
      default: return <Badge variant="outline" className="font-mono text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5"><Clock size={10} className="mr-1"/> PENDING OPEN</Badge>;
    }
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

  const statusColor = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "CONFIRMED") return "text-emerald-400 border-emerald-500/30 bg-emerald-500/5";
    if (s === "WEAKENED") return "text-amber-400 border-amber-500/30 bg-amber-500/5";
    if (s === "INVALIDATED") return "text-red-400 border-red-500/30 bg-red-500/5";
    return "text-zinc-400 border-border bg-secondary/50";
  };

  return (
    <div className="p-5 space-y-5" data-ocid="market-open.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-blue-500" />
          <span className="font-mono text-[12px] font-bold text-foreground uppercase tracking-widest">
            Agent 2: Market Open Confirmation
          </span>
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 h-4 border-blue-500/30 text-blue-400 bg-blue-500/5 ml-2">
            9:15 - 9:20 AM
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {status && (
            <Badge variant="outline" className="font-mono text-[9px] px-2 py-0.5 border-border text-muted-foreground">
              <Clock size={8} className="mr-1" />
              Last Run: {status.last_run_time || "Never"}
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
            onClick={triggerConfirm}
            disabled={runningConfirm}
            className="font-mono text-[10px] h-6 bg-blue-600 text-white hover:bg-blue-700 shadow-[0_0_15px_rgba(37,99,235,0.3)]"
          >
            {runningConfirm ? (
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Confirming...</>
            ) : (
              <><CheckCircle2 size={10} className="mr-1" /> Run Market Open Analysis</>
            )}
          </Button>
        </div>
      </div>

      <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4 mb-4">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong>How it works:</strong> Agent 2 validates the Discovery thesis against the actual opening session (9:15–9:20 AM). It evaluates gap direction, opening move quality, and price discovery to determine if the edge is <strong className="text-emerald-400">CONFIRMED (TRADE)</strong> or <strong className="text-red-400">INVALIDATED (NO TRADE)</strong>. Direction (BULLISH / BEARISH) is set by Agent 1's combined view.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "PENDING", count: summary.pending, icon: <Clock size={16} />, color: "text-blue-400", bg: "bg-blue-500/5 border-blue-500/20" },
          { label: "CONFIRMED", count: summary.confirmed, icon: <CheckCircle2 size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20" },
          { label: "REVISED", count: summary.revised, icon: <RefreshCw size={16} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20" },
          { label: "INVALIDATED", count: summary.invalidated, icon: <Ban size={16} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn("border rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-all hover:scale-[1.02]", item.bg)}
            onClick={() => setConfFilter(confFilter === item.label ? "ALL" : item.label)}
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
      <div className="flex items-center justify-between flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest mr-1">Status:</span>
          {["ALL", "PENDING", "CONFIRMED", "INVALIDATED"].map((s) => (
            <Badge
              key={s}
              variant="outline"
              className={cn(
                "font-mono text-[9px] px-2 py-0.5 cursor-pointer transition-all",
                confFilter === s
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/30"
              )}
              onClick={() => setConfFilter(s)}
            >
              {s}
            </Badge>
          ))}
        </div>

        <span className="font-mono text-[9px] text-muted-foreground">
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
          <Activity size={32} className="mx-auto text-muted-foreground opacity-20" />
          <p className="font-mono text-xs text-muted-foreground">No signals to display</p>
          <p className="font-mono text-[10px] text-muted-foreground opacity-50">
            Agent 1 must run first to generate candidate watchlist signals.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const reasoning = sig.reasoning || {};
            const cv = reasoning.combined_view || {};
            const cData = sig.confirmation_data || {};
            const hasConfirmation = cData && Object.keys(cData).length > 0 && sig.confirmation_status !== "pending";
            const isTrade = cData?.decision?.should_pass_to_agent_3 === true;
            const direction = cv.final_bias || "NEUTRAL";
            const valStatus = cData?.validation?.status || "PENDING";

            return (
              <div
                key={sig.id}
                className={cn(
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  sig.confirmation_status === "invalidated" ? "opacity-50 grayscale border-border" : "border-border"
                )}
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Direction + Status */}
                    <div className="flex items-center gap-3">
                       <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                         {directionIcon(direction)}
                       </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className={cn("font-mono text-[9px] uppercase tracking-widest font-bold", directionColor(direction))}>
                          {hasConfirmation ? direction : "AWAITING OPEN"}
                        </div>
                      </div>
                      <div className="ml-2 border-l border-border/50 pl-4">
                        {confirmationBadge(sig.confirmation_status)}
                      </div>
                    </div>

                    {/* Right: Agent 2 Summary */}
                    {hasConfirmation && (
                       <div className="flex items-center gap-4 hidden md:flex text-right">
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Decision</div>
                             <div className={cn("font-mono text-xs font-bold",
                                isTrade ? "text-emerald-400" : "text-red-400"
                             )}>
                                {isTrade ? "TRADE" : "NO TRADE"}
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Alignment</div>
                             <div className="font-mono text-xs font-bold text-foreground">
                                {cData.thesis_check?.alignment || "—"}
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Validation</div>
                             <Badge variant="outline" className={cn("font-mono text-[9px]", statusColor(valStatus))}>
                               {valStatus}
                             </Badge>
                          </div>
                       </div>
                    )}
                    
                    <div className="text-muted-foreground">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>

                  {/* Event Summary (always visible) */}
                  {cv.executive_summary && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1 italic">
                      "{cv.executive_summary}"
                    </p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">

                    {/* Agent 2 Confirmation Panel */}
                    {hasConfirmation ? (
                      <div className="space-y-4">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={12} className="text-blue-400" />
                          <span className="font-mono text-[10px] text-blue-400 uppercase tracking-widest font-semibold">Agent 2 Edge Validation</span>
                        </div>

                        {/* Decision + Key Metrics Row */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pb-4 border-b border-border/30">
                          <div className={cn("bg-background/50 rounded p-3 border border-l-2", isTrade ? "border-emerald-500/30 border-l-emerald-500" : "border-red-500/30 border-l-red-500")}>
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Decision</div>
                            <div className={cn("font-mono text-sm font-bold", isTrade ? "text-emerald-400" : "text-red-400")}>
                              {isTrade ? "TRADE" : "NO TRADE"}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50 border-l-2 border-l-primary">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Validation Status</div>
                            <div className={cn("font-mono text-sm font-bold", statusColor(valStatus).split(' ')[0])}>
                              {valStatus}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Trade Mode</div>
                            <div className="font-mono text-sm font-bold text-foreground">
                              {cData.trade_suitability?.mode || "—"}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Priority</div>
                            <div className="font-mono text-sm font-bold text-foreground">
                              {cData.trade_suitability?.priority || "—"}
                            </div>
                          </div>
                        </div>

                        {/* Why Tradable / Not */}
                        <div className={cn("p-3 rounded border shadow-sm border-l-2", isTrade ? "bg-emerald-500/5 border-emerald-500/20 border-l-emerald-500" : "bg-red-500/5 border-red-500/20 border-l-red-500")}>
                          <div className="flex items-center gap-1 mb-1">
                            <Target size={10} className={isTrade ? "text-emerald-400" : "text-red-400"} />
                            <span className={cn("font-mono text-[9px] uppercase tracking-widest font-semibold", isTrade ? "text-emerald-400" : "text-red-400")}>
                              Agent 3 Instruction
                            </span>
                          </div>
                          <p className="text-xs text-foreground leading-relaxed">{cData.decision?.agent_3_instruction}</p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {/* Thesis Check */}
                          <div className="space-y-3">
                            <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 border-l-2 border-l-zinc-500 shadow-sm">
                              <div className="font-mono text-[9px] uppercase tracking-widest font-semibold mb-1 opacity-80">Validation Reason</div>
                              <p className="text-xs">{cData.validation?.reason}</p>
                            </div>
                            <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 border-l-2 border-l-emerald-500 shadow-sm">
                              <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest font-semibold mb-1">Supporting Evidence</div>
                              <ul className="space-y-0.5">
                                {cData.thesis_check?.supporting_evidence?.map((c: string, i: number) => (
                                  <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                    <CheckCircle2 size={9} className="text-emerald-400 mt-0.5 shrink-0" />
                                    {c}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          {/* Market Behavior & Contradicting Evidence */}
                          <div className="space-y-3">
                             <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 border-l-2 border-l-amber-500 shadow-sm">
                              <div className="font-mono text-[9px] text-amber-400 uppercase tracking-widest font-semibold mb-1">Market Behavior</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Price:</strong> {cData.market_behavior?.price_behavior}</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Volume:</strong> {cData.market_behavior?.volume_behavior}</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Volatility:</strong> {cData.market_behavior?.volatility_behavior}</div>
                            </div>
                            
                            {cData.thesis_check?.contradicting_evidence && cData.thesis_check.contradicting_evidence.length > 0 && (
                              <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 border-l-2 border-l-rose-500 shadow-sm">
                                <div className="font-mono text-[9px] text-rose-400 uppercase tracking-widest font-semibold mb-1">Contradicting Evidence</div>
                                <ul className="space-y-0.5">
                                  {cData.thesis_check.contradicting_evidence.map((c: string, i: number) => (
                                    <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                      <AlertTriangle size={9} className="text-rose-400 mt-0.5 shrink-0" />
                                      {c}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Indicators to check */}
                        <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 shadow-sm border-l-2 border-l-blue-500">
                          <div className="font-mono text-[9px] text-blue-400 uppercase tracking-widest font-semibold mb-1">Indicators for Agent 3</div>
                          <div className="flex flex-wrap gap-2 pt-1">
                            {Object.entries(cData.indicators_to_check || {}).map(([key, vals]: [string, any]) => {
                               if (!vals || vals.length === 0) return null;
                               return (
                                 <div key={key} className="flex gap-1 items-center bg-secondary/50 px-2 py-1 rounded">
                                   <span className="text-[9px] font-mono text-muted-foreground uppercase">{key}:</span>
                                   <span className="text-[10px]">{vals.join(', ')}</span>
                                 </div>
                               );
                            })}
                          </div>
                        </div>

                        {/* Source Meta */}
                        <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground">
                          <span>Source: <span className="text-foreground">{cData._source || "unknown"}</span></span>
                          {cData._model && <span>Model: <span className="text-foreground">{cData._model}</span></span>}
                        </div>
                      </div>
                    ) : (
                      <div className="bg-background/50 rounded p-4 border border-border/50 text-center">
                         <Clock size={20} className="mx-auto text-muted-foreground opacity-50 mb-2" />
                         <p className="font-mono text-xs text-muted-foreground">Waiting for Agent 2 Confirmation...</p>
                         <p className="text-[10px] text-muted-foreground opacity-60 mt-1">This signal was generated pre-market. It will be validated against live data at 9:20 AM.</p>
                      </div>
                    )}

                    {/* Agent 1 Discovery context */}
                    {cv.combined_trading_thesis && (
                      <div className="pt-2 border-t border-border/30">
                        <div className="bg-background/50 rounded p-3 border border-border/50 border-l-2 border-l-zinc-500">
                          <div className="flex items-center gap-2 mb-1">
                            <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Agent 1 Pre-Market Thesis</div>
                          </div>
                          <p className="text-[11px] text-muted-foreground leading-relaxed italic">
                            "{cv.combined_trading_thesis}"
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Footer */}
      <div className="font-mono text-[9px] text-muted-foreground opacity-25 text-center tracking-widest pb-1 border-t border-border/20 pt-3 mt-6">
        -- AGENT 2 . EDGE VALIDATION . MARKET OPEN INTELLIGENCE --
      </div>
    </div>
  );
}
