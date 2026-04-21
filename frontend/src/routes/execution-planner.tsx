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
  Crosshair,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertTriangle,
  Ban,
  Activity,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowUpCircle,
  ArrowDownCircle,
  Target,
  Navigation
} from "lucide-react";

export const Route = createFileRoute("/execution-planner")({
  component: ExecutionPlannerPage,
});

function ExecutionPlannerPage() {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [runningExec, setRunningExec] = useState(false);
  const [execFilter, setExecFilter] = useState<string>("ALL");
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

  const triggerExec = async () => {
    setRunningExec(true);
    try {
      await api.triggerExecutionRun();
      await loadSignals();
    } catch (err) {
      console.error("Agent execution run failed", err);
    } finally {
      setRunningExec(false);
    }
  };

  const signals = data?.signals || [];
  
  // Filter only signals that have passed Agent 2 confirmation, OR that have already been processed by Agent 3
  const executionSignals = signals.filter((s: any) => 
    s.confirmation_status === "confirmed" || s.execution_status === "planned" || s.execution_status === "skipped"
  );

  const filtered = executionSignals.filter((s: any) => {
    if (execFilter !== "ALL" && s.execution_status !== execFilter.toLowerCase()) return false;
    return true;
  });

  const eStatus = status?.execution_stats || { planned: 0, pending: 0 };
  const totalSkipped = executionSignals.filter((s: any) => s.execution_status === "skipped").length;

  const confidenceColor = (conf: number) => {
    if (conf >= 80) return "text-emerald-400";
    if (conf >= 60) return "text-amber-400";
    if (conf >= 40) return "text-orange-400";
    return "text-red-400";
  };

  const executionBadge = (status: string) => {
    switch (status) {
      case "planned": return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5"><Crosshair size={10} className="mr-1"/> PLANNED</Badge>;
      case "skipped": return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5"><Ban size={10} className="mr-1"/> SKIPPED</Badge>;
      default: return <Badge variant="outline" className="font-mono text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5"><Clock size={10} className="mr-1"/> PENDING EXEC</Badge>;
    }
  };

  const actionColor = (action: string) => {
    const a = (action || "").toUpperCase();
    if (a === "BUY") return "text-emerald-400";
    if (a === "SELL") return "text-red-400";
    if (a === "WAIT") return "text-amber-400";
    return "text-zinc-500";
  };

  const execDecisionBadge = (decision: string) => {
    const d = (decision || "").toUpperCase();
    if (d === "ENTER NOW") return <Badge variant="outline" className="font-mono text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5">ENTER NOW</Badge>;
    if (d === "WAIT FOR PULLBACK") return <Badge variant="outline" className="font-mono text-[9px] border-amber-500/30 text-amber-400 bg-amber-500/5">WAIT FOR PULLBACK</Badge>;
    if (d === "WAIT FOR BREAKOUT") return <Badge variant="outline" className="font-mono text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5">WAIT FOR BREAKOUT</Badge>;
    if (d === "AVOID CHASE") return <Badge variant="outline" className="font-mono text-[9px] border-orange-500/30 text-orange-400 bg-orange-500/5">AVOID CHASE</Badge>;
    if (d === "NO TRADE") return <Badge variant="outline" className="font-mono text-[9px] border-red-500/30 text-red-400 bg-red-500/5">NO TRADE</Badge>;
    return <Badge variant="outline" className="font-mono text-[9px] border-zinc-500/30 text-zinc-400 bg-zinc-500/5">{d || "—"}</Badge>;
  };

  return (
    <div className="p-5 space-y-5" data-ocid="execution-planner.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Navigation size={16} className="text-indigo-400" />
          <span className="font-mono text-[12px] font-bold text-foreground uppercase tracking-widest">
            Agent 3: Execution Planner
          </span>
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 h-4 border-indigo-500/30 text-indigo-400 bg-indigo-500/5 ml-2">
            LIVE ENTRY
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
            onClick={triggerExec}
            disabled={runningExec}
            className="font-mono text-[10px] h-6 bg-indigo-600 text-white hover:bg-indigo-700 shadow-[0_0_15px_rgba(79,70,229,0.3)]"
          >
            {runningExec ? (
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Planning...</>
            ) : (
              <><Crosshair size={10} className="mr-1" /> Run Execution Planner</>
            )}
          </Button>
        </div>
      </div>

      <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-lg p-4 mb-4">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong>How it works:</strong> Agent 3 takes trades validated by Agent 2 and analyzes live intraday structure (VWAP, price extensions) to formulate precise entry, stoploss, and target plans. It prevents chasing extended moves and optimizes risk-reward.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {[
          { label: "PENDING", count: eStatus.pending, icon: <Clock size={16} />, color: "text-blue-400", bg: "bg-blue-500/5 border-blue-500/20" },
          { label: "PLANNED", count: eStatus.planned, icon: <Crosshair size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20" },
          { label: "SKIPPED", count: totalSkipped, icon: <Ban size={16} />, color: "text-red-400", bg: "bg-red-500/5 border-red-500/20" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn("border rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-all hover:scale-[1.02]", item.bg)}
            onClick={() => setExecFilter(execFilter === item.label ? "ALL" : item.label)}
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
          {["ALL", "PENDING", "PLANNED", "SKIPPED"].map((s) => (
            <Badge
              key={s}
              variant="outline"
              className={cn(
                "font-mono text-[9px] px-2 py-0.5 cursor-pointer transition-all",
                execFilter === s
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/30"
              )}
              onClick={() => setExecFilter(s)}
            >
              {s}
            </Badge>
          ))}
        </div>

        <span className="font-mono text-[9px] text-muted-foreground">
          Showing {filtered.length} of {executionSignals.length} candidates
        </span>
      </div>

      {/* Signal Cards */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
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
          <Navigation size={32} className="mx-auto text-muted-foreground opacity-20" />
          <p className="font-mono text-xs text-muted-foreground">No valid trades ready for execution</p>
          <p className="font-mono text-[10px] text-muted-foreground opacity-50">
            Agent 2 must confirm edges before Agent 3 can plan execution.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const eData = sig.execution_data || {};
            const hasPlan = eData && Object.keys(eData).length > 0 && sig.execution_status !== "pending";
            
            // Reconstruct some of the A2 context
            const cData = sig.confirmation_data || {};
            const direction = cData.direction || "NEUTRAL";

            return (
              <div
                key={sig.id}
                className={cn(
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  sig.execution_status === "skipped" ? "opacity-60 grayscale border-border" : "border-border"
                )}
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Status */}
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                        <Crosshair size={14} className="text-indigo-400" />
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                           <span className={cn(direction === "BULLISH" ? "text-emerald-400" : direction === "BEARISH" ? "text-red-400" : "")}>{direction}</span> Edge Confirmed
                        </div>
                      </div>
                      <div className="ml-2 border-l border-border/50 pl-4">
                        {executionBadge(sig.execution_status)}
                      </div>
                    </div>

                    {/* Right: Agent 3 Summary */}
                    {hasPlan && (
                       <div className="flex items-center gap-4 hidden md:flex text-right">
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Action</div>
                             <div className={cn("font-mono text-xs font-bold", actionColor(eData.action))}>
                                {eData.action || "—"}
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Plan</div>
                             {execDecisionBadge(eData.execution_decision)}
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Confidence</div>
                             <div className={cn("font-mono text-xs font-bold", confidenceColor(eData.confidence || 0))}>
                                {eData.confidence || 0}%
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Target</div>
                             <div className="font-mono text-xs font-bold text-foreground">
                                {eData.target?.price ? `₹${eData.target.price}` : "—"}
                             </div>
                          </div>
                       </div>
                    )}
                    
                    <div className="text-muted-foreground">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>

                  {/* High level why */}
                  {hasPlan && eData.why_now_or_why_wait && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1">{eData.why_now_or_why_wait}</p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">

                    {hasPlan ? (
                      <div className="space-y-4">
                        <div className="flex items-center gap-2">
                          <Target size={12} className="text-indigo-400" />
                          <span className="font-mono text-[10px] text-indigo-400 uppercase tracking-widest font-semibold">Execution Blueprint</span>
                        </div>

                        {/* Top Line Decision */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pb-4 border-b border-border/30">
                          <div className={cn("bg-background/50 rounded p-3 border", eData.action !== "AVOID" ? "border-indigo-500/30" : "border-red-500/30")}>
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Action</div>
                            <div className={cn("font-mono text-sm font-bold", actionColor(eData.action))}>
                              {eData.action || "—"}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Decision</div>
                            <div className="mt-1">{execDecisionBadge(eData.execution_decision)}</div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Confidence</div>
                            <div className={cn("font-mono text-sm font-bold tabular-nums", confidenceColor(eData.confidence || 0))}>
                              {eData.confidence || 0}%
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Trade Mode</div>
                            <div className="font-mono text-sm font-bold text-foreground">
                              {eData.trade_mode || "—"}
                            </div>
                          </div>
                        </div>

                        {/* Price Levels */}
                        {eData.action !== "AVOID" && (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {/* Entry */}
                            <div className="bg-blue-500/5 rounded p-3 border border-blue-500/20">
                               <div className="font-mono text-[9px] text-blue-400 uppercase tracking-widest mb-1 font-semibold">Entry Plan</div>
                               <div className="text-lg font-bold text-foreground mb-1">
                                  {eData.entry_plan?.entry_price ? `₹${eData.entry_plan.entry_price}` : "MKT"}
                               </div>
                               <Badge variant="outline" className="font-mono text-[8px] bg-background/50 text-muted-foreground mb-2">
                                  TYPE: {eData.entry_plan?.entry_type || "NONE"}
                               </Badge>
                               <p className="text-[11px] text-muted-foreground">{eData.entry_plan?.condition}</p>
                            </div>

                            {/* Target */}
                            <div className="bg-emerald-500/5 rounded p-3 border border-emerald-500/20">
                               <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest mb-1 font-semibold">Target</div>
                               <div className="text-lg font-bold text-emerald-400 mb-1">
                                  {eData.target?.price ? `₹${eData.target.price}` : "—"}
                               </div>
                               <p className="text-[11px] text-muted-foreground">{eData.target?.reason}</p>
                            </div>

                            {/* Stoploss */}
                            <div className="bg-red-500/5 rounded p-3 border border-red-500/20">
                               <div className="font-mono text-[9px] text-red-400 uppercase tracking-widest mb-1 font-semibold">Stop Loss</div>
                               <div className="text-lg font-bold text-red-400 mb-1">
                                  {eData.stop_loss?.price ? `₹${eData.stop_loss.price}` : "—"}
                               </div>
                               <p className="text-[11px] text-muted-foreground">{eData.stop_loss?.reason}</p>
                            </div>
                          </div>
                        )}

                        {/* Context & Risk */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                           {eData.risk_reward && (
                              <div className="bg-background/50 p-3 rounded border border-border/50 flex items-center justify-between">
                                 <span className="font-mono text-[9px] text-muted-foreground uppercase">Est. Risk/Reward:</span>
                                 <span className="font-mono text-xs font-bold text-foreground">{eData.risk_reward}</span>
                              </div>
                           )}
                           {eData.invalidation && (
                              <div className="bg-background/50 p-3 rounded border border-border/50">
                                 <div className="font-mono text-[9px] text-orange-400 uppercase mb-1">Invalidation Trigger:</div>
                                 <p className="text-[11px] text-muted-foreground">{eData.invalidation}</p>
                              </div>
                           )}
                        </div>

                        {/* Position Sizing Block */}
                        {eData.position_sizing && eData.position_sizing.position_size_shares > 0 && (
                          <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <Activity size={11} className="text-emerald-400" />
                              <span className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest font-semibold">Position Sizing</span>
                            </div>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                              <div className="bg-background/50 rounded p-2 border border-border/30">
                                <div className="font-mono text-[8px] text-muted-foreground uppercase mb-0.5">Shares</div>
                                <div className="font-mono text-sm font-bold text-foreground">{eData.position_sizing.position_size_shares.toLocaleString()}</div>
                              </div>
                              <div className="bg-background/50 rounded p-2 border border-border/30">
                                <div className="font-mono text-[8px] text-muted-foreground uppercase mb-0.5">Capital Deployed</div>
                                <div className="font-mono text-sm font-bold text-amber-400">₹{eData.position_sizing.position_size_inr?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
                              </div>
                              <div className="bg-background/50 rounded p-2 border border-border/30">
                                <div className="font-mono text-[8px] text-muted-foreground uppercase mb-0.5">% of Capital</div>
                                <div className="font-mono text-sm font-bold text-blue-400">{eData.position_sizing.capital_used_pct}%</div>
                              </div>
                              <div className="bg-background/50 rounded p-2 border border-border/30">
                                <div className="font-mono text-[8px] text-muted-foreground uppercase mb-0.5">Max Loss at SL</div>
                                <div className="font-mono text-sm font-bold text-red-400">₹{eData.position_sizing.max_loss_at_sl?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</div>
                              </div>
                            </div>
                            {eData.position_sizing.sizing_note && (
                              <p className="font-mono text-[8px] text-muted-foreground opacity-50 mt-2">{eData.position_sizing.sizing_note}</p>
                            )}
                          </div>
                        )}

                        {/* Final Summary */}
                        {eData.final_summary && (
                          <div className="bg-indigo-500/5 border border-indigo-500/20 rounded p-3">
                            <div className="font-mono text-[9px] text-indigo-400 uppercase tracking-widest mb-1 font-semibold">Planner Summary</div>
                            <p className="text-xs text-foreground leading-relaxed font-medium">{eData.final_summary}</p>
                          </div>
                        )}
                        
                        {/* Source Meta */}
                        <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground">
                          <span>Source: <span className="text-foreground">{eData._source || "unknown"}</span></span>
                          {eData._model && <span>Model: <span className="text-foreground">{eData._model}</span></span>}
                        </div>
                      </div>
                    ) : (
                      <div className="bg-background/50 rounded p-4 border border-border/50 text-center">
                         <Clock size={20} className="mx-auto text-muted-foreground opacity-50 mb-2" />
                         <p className="font-mono text-xs text-muted-foreground">Waiting for Agent 3 Execution Plan...</p>
                         <p className="text-[10px] text-muted-foreground opacity-60 mt-1">This edge has been validated. Now waiting to map precise entry levels against live market action.</p>
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
        -- AGENT 3 . LIVE EXECUTION . ENTRY PLANNING --
      </div>
    </div>
  );
}
