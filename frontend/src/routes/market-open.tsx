import { useEffect, useState, useCallback } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api } from "@/backend";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Brain,
  RefreshCw,
  Clock,
  Target,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  BarChart3,
  Newspaper,
  CheckCircle2,
  AlertTriangle,
  Ban,
  Activity
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

  const formatNumber = (val: number | null) => {
    if (val === null || val === undefined) return "—";
    return val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const signals = data?.signals || [];
  const summary = data?.confirmation_summary || { pending: 0, confirmed: 0, revised: 0, invalidated: 0 };

  const filtered = signals.filter((s: any) => {
    if (confFilter !== "ALL" && s.confirmation_status !== confFilter.toLowerCase()) return false;
    return true;
  });

  const confirmationBadge = (status: string) => {
    switch (status) {
      case "confirmed": return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5"><CheckCircle2 size={10} className="mr-1"/> CONFIRMED</Badge>;
      case "revised": return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5"><RefreshCw size={10} className="mr-1"/> REVISED</Badge>;
      case "invalidated": return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5"><Ban size={10} className="mr-1"/> INVALIDATED</Badge>;
      default: return <Badge variant="outline" className="font-mono text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5"><Clock size={10} className="mr-1"/> PENDING OPEN</Badge>;
    }
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
          <strong>How it works:</strong> Agent 2 compares the pre-market signals (generated at 8:30 AM) against the actual opening session data (9:15-9:20 AM). It analyzes the gap direction, opening volume, and first 5-minute price action to definitively <strong className="text-emerald-400">CONFIRM</strong>, <strong className="text-amber-400">REVISE</strong>, or <strong className="text-red-400">INVALIDATE</strong> the trade.
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
          {["ALL", "PENDING", "CONFIRMED", "REVISED", "INVALIDATED"].map((s) => (
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
            Agent 1 must run first to generate candidate signals.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const reasoning = sig.reasoning || {};
            const snapshot = sig.stock_snapshot || {};
            const cData = sig.confirmation_data || {};

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
                    {/* Left: Symbol + Signal */}
                    <div className="flex items-center gap-3">
                       <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                          <span className={cn("font-bold text-sm", 
                             sig.signal_type === "BUY" ? "text-emerald-400" :
                             sig.signal_type === "SELL" ? "text-red-400" : "text-amber-400"
                          )}>
                             {sig.signal_type.charAt(0)}
                          </span>
                       </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">{sig.signal_type} · {sig.trade_mode}</div>
                      </div>
                      <div className="ml-2 border-l border-border/50 pl-4">
                        {confirmationBadge(sig.confirmation_status)}
                      </div>
                    </div>

                    {/* Right: Agent 2 Summary */}
                    {cData && Object.keys(cData).length > 0 && sig.confirmation_status !== "pending" && (
                       <div className="flex items-center gap-4 hidden md:flex text-right">
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Signal Type</div>
                             <div className={cn("font-mono text-xs font-bold", 
                                (cData.revised_signal_type ?? sig.signal_type) === "BUY" ? "text-emerald-400" : "text-red-400"
                             )}>
                                {cData.revised_signal_type ?? sig.signal_type}
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Confidence</div>
                             <div className="font-mono text-xs text-foreground">
                                {Math.round((cData.revised_confidence ?? sig.confidence) * 100)}%
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Gap Assessment</div>
                             <div className="font-mono text-xs text-foreground">{cData.gap_type?.replace(/_/g, " ")}</div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Volume</div>
                             <div className={cn("font-mono text-xs", cData.volume_assessment === "strong" ? "text-emerald-400" : "text-foreground")}>
                                {cData.volume_assessment}
                             </div>
                          </div>
                       </div>
                    )}
                    
                    <div className="text-muted-foreground">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    
                    {/* Trade Parameters row */}
                    <div className="grid grid-cols-4 gap-2 pb-4 border-b border-border/30">
                      <div>
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">Entry</div>
                        <div className="font-mono text-sm font-bold text-foreground tabular-nums">
                          {formatNumber(cData.revised_entry ?? sig.entry_price)}
                          {cData.revised_entry && cData.revised_entry !== sig.entry_price && (
                            <span className="text-[10px] text-muted-foreground line-through ml-1.5 opacity-50 font-normal">
                              {formatNumber(sig.entry_price)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-red-400 uppercase">Stop Loss</div>
                        <div className="font-mono text-sm font-bold text-red-400 tabular-nums">
                          {formatNumber(cData.revised_stop_loss ?? sig.stop_loss)}
                          {cData.revised_stop_loss && cData.revised_stop_loss !== sig.stop_loss && (
                            <span className="text-[10px] text-muted-foreground line-through ml-1.5 opacity-50 font-normal">
                              {formatNumber(sig.stop_loss)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-emerald-400 uppercase">Target</div>
                        <div className="font-mono text-sm font-bold text-emerald-400 tabular-nums">
                          {formatNumber(cData.revised_target ?? sig.target_price)}
                          {cData.revised_target && cData.revised_target !== sig.target_price && (
                            <span className="text-[10px] text-muted-foreground line-through ml-1.5 opacity-50 font-normal">
                              {formatNumber(sig.target_price)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="font-mono text-[8px] text-muted-foreground uppercase">R:R</div>
                        <div className="font-mono text-sm text-foreground tabular-nums">
                          {(() => {
                            const entry = cData.revised_entry ?? sig.entry_price;
                            const sl = cData.revised_stop_loss ?? sig.stop_loss;
                            const target = cData.revised_target ?? sig.target_price;
                            if (entry && sl && target) {
                              const risk = Math.abs(entry - sl);
                              if (risk > 0) return (Math.abs(target - entry) / risk).toFixed(2);
                            }
                            return sig.risk_reward;
                          })()}x
                        </div>
                      </div>
                    </div>

                    {/* Agent 2 Confirmation Panel */}
                    {cData && Object.keys(cData).length > 0 && sig.confirmation_status !== "pending" ? (
                      <div className="space-y-4">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={12} className="text-blue-400" />
                          <span className="font-mono text-[10px] text-blue-400 uppercase tracking-widest font-semibold">Live Open Data & Analysis</span>
                        </div>
                        
                        {cData.reasoning && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {cData.reasoning.gap_assessment && (
                              <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Gap Assessment</span>
                                <p className="text-xs text-foreground leading-relaxed">{cData.reasoning.gap_assessment}</p>
                              </div>
                            )}
                            {cData.reasoning.volume_analysis && (
                              <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">Volume Confirmation</span>
                                <p className="text-xs text-foreground leading-relaxed">{cData.reasoning.volume_analysis}</p>
                              </div>
                            )}
                            {cData.reasoning.price_action && (
                              <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50">
                                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold">First 5-Min Price Action</span>
                                <p className="text-xs text-foreground leading-relaxed">{cData.reasoning.price_action}</p>
                              </div>
                            )}
                            {cData.reasoning.final_recommendation && (
                              <div className="space-y-1 bg-blue-500/10 p-3 rounded border border-blue-500/20">
                                <span className="font-mono text-[9px] text-blue-400 uppercase tracking-widest font-semibold">Final Verdict</span>
                                <p className="text-xs text-foreground leading-relaxed font-bold">{cData.reasoning.final_recommendation}</p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="bg-background/50 rounded p-4 border border-border/50 text-center">
                         <Clock size={20} className="mx-auto text-muted-foreground opacity-50 mb-2" />
                         <p className="font-mono text-xs text-muted-foreground">Waiting for Agent 2 Confirmation...</p>
                         <p className="text-[10px] text-muted-foreground opacity-60 mt-1">This signal was generated pre-market. It will be verified against live data at 9:20 AM.</p>
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
        -- AGENT 2 . MARKET OPEN INTELLIGENCE . LIVE CONFIRMATION --
      </div>
    </div>
  );
}
