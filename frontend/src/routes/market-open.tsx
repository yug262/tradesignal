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
  CheckCircle2,
  AlertTriangle,
  Ban,
  Activity,
  ArrowUpCircle,
  ArrowDownCircle,
  Minus,
  Info,
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

  const directionIcon = (dir: string) => {
    const d = (dir || "").toUpperCase();
    if (d === "BULLISH") return <ArrowUpCircle size={18} className="text-emerald-400" />;
    if (d === "BEARISH") return <ArrowDownCircle size={18} className="text-red-400" />;
    return <Minus size={18} className="text-zinc-400" />;
  };

  const directionColor = (dir: string) => {
    const d = (dir || "").toUpperCase();
    if (d === "BULLISH") return "text-emerald-400";
    if (d === "BEARISH") return "text-red-400";
    return "text-zinc-400";
  };

  const confirmationBadge = (status: string) => {
    switch (status) {
      case "confirmed": return <Badge variant="outline" className="text-[10px] font-semibold border-emerald-500/30 text-emerald-400 bg-emerald-500/5 rounded-full px-2.5"><CheckCircle2 size={11} className="mr-1"/> CONFIRMED</Badge>;
      case "revised": return <Badge variant="outline" className="text-[10px] font-semibold border-amber-500/30 text-amber-400 bg-amber-500/5 rounded-full px-2.5"><RefreshCw size={11} className="mr-1"/> REVISED</Badge>;
      case "invalidated": return <Badge variant="outline" className="text-[10px] font-semibold border-red-500/30 text-red-400 bg-red-500/5 rounded-full px-2.5"><Ban size={11} className="mr-1"/> INVALIDATED</Badge>;
      default: return <Badge variant="outline" className="text-[10px] font-semibold border-blue-500/30 text-blue-400 bg-blue-500/5 rounded-full px-2.5"><Clock size={11} className="mr-1"/> PENDING</Badge>;
    }
  };

  const statusColor = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "CONFIRMED") return "text-emerald-400 border-emerald-500/30 bg-emerald-500/5";
    if (s === "WEAKENED") return "text-amber-400 border-amber-500/30 bg-amber-500/5";
    if (s === "INVALIDATED") return "text-red-400 border-red-500/30 bg-red-500/5";
    return "text-zinc-400 border-border bg-secondary/50";
  };

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto" data-ocid="market-open.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4 animate-fade-up">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-blue-500/15 text-blue-400">
              <Activity size={20} />
            </div>
            <div>
              <h2 className="font-display text-xl font-bold text-foreground tracking-tight">
                Market Open Validation
              </h2>
              <p className="text-[12px] text-muted-foreground">
                Agent 2 validates discoveries against live opening data (9:15–9:20 AM) — decides TRADE or NO TRADE
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
          <Button variant="outline" size="sm" onClick={loadSignals} disabled={loading} className="text-[12px] h-8 border-border rounded-lg">
            <RefreshCw size={13} className={cn("mr-1.5", loading && "animate-spin")} />
            Refresh
          </Button>
          <Button size="sm" onClick={triggerConfirm} disabled={runningConfirm}
            className="text-[12px] h-8 bg-blue-600 text-white hover:bg-blue-700 rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.2)]">
            {runningConfirm ? (
              <><RefreshCw size={13} className="mr-1.5 animate-spin" /> Confirming...</>
            ) : (
              <><CheckCircle2 size={13} className="mr-1.5" /> Run Validation</>
            )}
          </Button>
        </div>
      </div>

      {/* How it works */}
      <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4 flex items-start gap-3 animate-fade-up stagger-1">
        <Info size={16} className="text-blue-400 mt-0.5 shrink-0" />
        <p className="text-sm text-muted-foreground leading-relaxed">
          <strong className="text-foreground">How it works:</strong> Agent 2 validates the Discovery thesis against the actual opening session. It evaluates gap direction, opening move quality, and price discovery to determine if the edge is <strong className="text-emerald-400">CONFIRMED</strong> or <strong className="text-red-400">INVALIDATED</strong>.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 animate-fade-up stagger-2">
        {[
          { label: "Pending", count: summary.pending, icon: <Clock size={18} />, color: "text-blue-400", bg: "bg-blue-500/5 border-blue-500/20 hover:bg-blue-500/10" },
          { label: "Confirmed", count: summary.confirmed, icon: <CheckCircle2 size={18} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20 hover:bg-emerald-500/10" },
          { label: "Revised", count: summary.revised, icon: <RefreshCw size={18} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20 hover:bg-amber-500/10" },
          { label: "Invalidated", count: summary.invalidated, icon: <Ban size={18} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20 hover:bg-red-500/10" },
        ].map((item) => (
          <div key={item.label}
            className={cn("border rounded-xl p-4 flex items-center gap-3 cursor-pointer transition-all duration-200 hover:scale-[1.02]", item.bg)}
            onClick={() => setConfFilter(confFilter === item.label.toUpperCase() ? "ALL" : item.label.toUpperCase())}>
            <div className={item.color}>{item.icon}</div>
            <div>
              <div className={cn("text-2xl font-bold font-mono tabular-nums", item.color)}>{item.count}</div>
              <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">{item.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center justify-between flex-wrap gap-2 animate-fade-up stagger-3">
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-muted-foreground mr-1">Status:</span>
          {["ALL", "PENDING", "CONFIRMED", "INVALIDATED"].map((s) => (
            <Badge key={s} variant="outline"
              className={cn("text-[11px] px-3 py-1 cursor-pointer transition-all rounded-full",
                confFilter === s ? "bg-primary/10 border-primary/30 text-primary" : "border-border text-muted-foreground hover:border-primary/30"
              )}
              onClick={() => setConfFilter(s)}>
              {s}
            </Badge>
          ))}
        </div>
        <span className="text-[12px] text-muted-foreground">
          Showing {filtered.length} of {signals.length} signals
        </span>
      </div>

      {/* Signal Cards */}
      {loading ? (
        <div className="space-y-3">{[1, 2, 3].map((i) => (
          <div key={i} className="bg-card border border-border rounded-xl p-5 space-y-3">
            <div className="flex justify-between"><Skeleton className="h-6 w-32" /><Skeleton className="h-5 w-20" /></div>
            <Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/4" />
          </div>
        ))}</div>
      ) : filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-16 text-center space-y-4 animate-fade-up">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-secondary mx-auto">
            <Activity size={28} className="text-muted-foreground/30" />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">No signals to display</p>
            <p className="text-xs text-muted-foreground mt-1">Agent 1 must run first to generate candidate watchlist signals.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3 animate-fade-up stagger-3">
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
              <div key={sig.id}
                className={cn("bg-card border rounded-xl overflow-hidden transition-all",
                  sig.confirmation_status === "invalidated" ? "opacity-50 border-border" : "border-border hover:border-primary/20"
                )}>
                {/* Main Row */}
                <div className="p-5 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}>
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-10 h-10 rounded-lg border border-border bg-secondary">
                        {directionIcon(direction)}
                      </div>
                      <div>
                        <h3 className="font-bold text-base text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className={cn("text-[11px] uppercase tracking-wider font-semibold", directionColor(direction))}>
                          {hasConfirmation ? direction : "AWAITING OPEN"}
                        </div>
                      </div>
                      <div className="ml-2 border-l border-border/50 pl-4">
                        {confirmationBadge(sig.confirmation_status)}
                      </div>
                    </div>

                    {hasConfirmation && (
                      <div className="flex items-center gap-5 hidden md:flex text-right">
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Decision</div>
                          <div className={cn("font-mono text-sm font-bold", isTrade ? "text-emerald-400" : "text-red-400")}>
                            {isTrade ? "TRADE" : "NO TRADE"}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Alignment</div>
                          <div className="font-mono text-sm font-bold text-foreground">
                            {cData.thesis_check?.alignment || "—"}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Validation</div>
                          <Badge variant="outline" className={cn("text-[10px] rounded-full", statusColor(valStatus))}>
                            {valStatus}
                          </Badge>
                        </div>
                      </div>
                    )}
                    
                    <div className="text-muted-foreground">
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
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
                    {hasConfirmation ? (
                      <div className="space-y-4">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={14} className="text-blue-400" />
                          <span className="text-[12px] text-blue-400 uppercase tracking-wider font-semibold">Agent 2 Edge Validation</span>
                        </div>

                        {/* Decision + Key Metrics Row */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          <div className={cn("bg-background/50 rounded-xl p-4 border border-l-[3px]", isTrade ? "border-emerald-500/30 border-l-emerald-500" : "border-red-500/30 border-l-red-500")}>
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Decision</div>
                            <div className={cn("font-mono text-lg font-bold", isTrade ? "text-emerald-400" : "text-red-400")}>
                              {isTrade ? "TRADE" : "NO TRADE"}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded-xl p-4 border border-border/50 border-l-[3px] border-l-primary">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Validation</div>
                            <div className={cn("font-mono text-lg font-bold", statusColor(valStatus).split(' ')[0])}>
                              {valStatus}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded-xl p-4 border border-border/50">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Trade Mode</div>
                            <div className="font-mono text-lg font-bold text-foreground">
                              {cData.trade_suitability?.mode || "—"}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded-xl p-4 border border-border/50">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Priority</div>
                            <div className="font-mono text-lg font-bold text-foreground">
                              {cData.trade_suitability?.priority || "—"}
                            </div>
                          </div>
                        </div>

                        {/* Agent 3 Instruction */}
                        <div className={cn("p-4 rounded-xl border border-l-[3px]", isTrade ? "bg-emerald-500/5 border-emerald-500/20 border-l-emerald-500" : "bg-red-500/5 border-red-500/20 border-l-red-500")}>
                          <div className="flex items-center gap-1.5 mb-2">
                            <Target size={12} className={isTrade ? "text-emerald-400" : "text-red-400"} />
                            <span className={cn("text-[11px] uppercase tracking-wider font-semibold", isTrade ? "text-emerald-400" : "text-red-400")}>
                              Instruction for Agent 3
                            </span>
                          </div>
                          <p className="text-sm text-foreground leading-relaxed">{cData.decision?.agent_3_instruction}</p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div className="space-y-3">
                            <div className="bg-background/50 p-4 rounded-xl border border-border/50 border-l-[3px] border-l-zinc-500">
                              <div className="text-[11px] uppercase tracking-wider font-semibold mb-2 text-muted-foreground">Validation Reason</div>
                              <p className="text-sm leading-relaxed">{cData.validation?.reason}</p>
                            </div>
                            <div className="bg-background/50 p-4 rounded-xl border border-border/50 border-l-[3px] border-l-emerald-500">
                              <div className="text-[11px] text-emerald-400 uppercase tracking-wider font-semibold mb-2">Supporting Evidence</div>
                              <ul className="space-y-1.5">
                                {cData.thesis_check?.supporting_evidence?.map((c: string, i: number) => (
                                  <li key={i} className="text-[12px] text-muted-foreground flex items-start gap-2">
                                    <CheckCircle2 size={11} className="text-emerald-400 mt-0.5 shrink-0" /> {c}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          <div className="space-y-3">
                            <div className="bg-background/50 p-4 rounded-xl border border-border/50 border-l-[3px] border-l-amber-500">
                              <div className="text-[11px] text-amber-400 uppercase tracking-wider font-semibold mb-2">Market Behavior</div>
                              <div className="space-y-1.5 text-[12px] text-muted-foreground">
                                <div><strong className="text-foreground">Price:</strong> {cData.market_behavior?.price_behavior}</div>
                                <div><strong className="text-foreground">Volume:</strong> {cData.market_behavior?.volume_behavior}</div>
                                <div><strong className="text-foreground">Volatility:</strong> {cData.market_behavior?.volatility_behavior}</div>
                              </div>
                            </div>
                            
                            {cData.thesis_check?.contradicting_evidence && cData.thesis_check.contradicting_evidence.length > 0 && (
                              <div className="bg-background/50 p-4 rounded-xl border border-border/50 border-l-[3px] border-l-rose-500">
                                <div className="text-[11px] text-rose-400 uppercase tracking-wider font-semibold mb-2">Contradicting Evidence</div>
                                <ul className="space-y-1.5">
                                  {cData.thesis_check.contradicting_evidence.map((c: string, i: number) => (
                                    <li key={i} className="text-[12px] text-muted-foreground flex items-start gap-2">
                                      <AlertTriangle size={11} className="text-rose-400 mt-0.5 shrink-0" /> {c}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Indicators */}
                        <div className="bg-background/50 p-4 rounded-xl border border-border/50 border-l-[3px] border-l-blue-500">
                          <div className="text-[11px] text-blue-400 uppercase tracking-wider font-semibold mb-2">Indicators for Agent 3</div>
                          <div className="flex flex-wrap gap-2 pt-1">
                            {Object.entries(cData.indicators_to_check || {}).map(([key, vals]: [string, any]) => {
                               if (!vals || vals.length === 0) return null;
                               return (
                                 <div key={key} className="flex gap-1 items-center bg-secondary/50 px-3 py-1.5 rounded-lg">
                                   <span className="text-[10px] font-mono text-muted-foreground uppercase">{key}:</span>
                                   <span className="text-[11px]">{vals.join(', ')}</span>
                                 </div>
                               );
                            })}
                          </div>
                        </div>

                        {/* Source Meta */}
                        <div className="flex items-center gap-4 pt-3 border-t border-border/30 text-[11px] font-mono text-muted-foreground/60">
                          <span>Source: <span className="text-foreground">{cData._source || "unknown"}</span></span>
                          {cData._model && <span>Model: <span className="text-foreground">{cData._model}</span></span>}
                        </div>
                      </div>
                    ) : (
                      <div className="bg-background/50 rounded-xl p-8 border border-border/50 text-center space-y-2">
                        <Clock size={24} className="mx-auto text-muted-foreground/40" />
                        <p className="text-sm font-medium text-foreground">Waiting for Agent 2 Confirmation</p>
                        <p className="text-xs text-muted-foreground">This signal was generated pre-market. It will be validated against live data at 9:20 AM.</p>
                      </div>
                    )}

                    {/* Agent 1 context */}
                    {cv.combined_trading_thesis && (
                      <div className="pt-3 border-t border-border/30">
                        <div className="bg-background/50 rounded-xl p-4 border border-border/50 border-l-[3px] border-l-zinc-500">
                          <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold mb-2">Agent 1 Pre-Market Thesis</div>
                          <p className="text-sm text-muted-foreground leading-relaxed italic">
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
    </div>
  );
}
