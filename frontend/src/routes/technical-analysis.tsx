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
  BarChart2,
  CheckCircle2,
  Activity,
  ArrowUpCircle,
  ArrowDownCircle,
  Minus,
  Navigation,
  LineChart,
} from "lucide-react";

export const Route = createFileRoute("/technical-analysis")({
  component: TechnicalAnalysisPage,
});

function TechnicalAnalysisPage() {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [runningTA, setRunningTA] = useState(false);
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

  const triggerTA = async () => {
    setRunningTA(true);
    try {
      await api.triggerTechnicalAnalysis();
      await loadSignals();
    } catch (err) {
      console.error("Agent 2.5 TA run failed", err);
    } finally {
      setRunningTA(false);
    }
  };

  const signals = data?.signals || [];

  // Filter signals that have passed Agent 2 confirmation
  const taSignals = signals.filter((s: any) => 
    s.confirmation_status === "confirmed" || s.execution_status === "planned" || s.execution_status === "skipped"
  );

  const filtered = taSignals.filter((s: any) => {
    const eData = s.execution_data || {};
    const hasTA = eData._has_agent25 === true;
    
    if (filter === "ANALYZED" && !hasTA) return false;
    if (filter === "PENDING" && hasTA) return false;
    
    // Check GO/NO GO
    const goNoGo = eData.technical_analysis_data?.agent_3_handoff?.technical_go_no_go || "WAIT";
    if (filter === "GO" && goNoGo !== "GO") return false;
    if (filter === "WAIT/NO_GO" && hasTA && goNoGo === "GO") return false;
    
    return true;
  });

  const pendingCount = taSignals.filter((s: any) => !(s.execution_data?._has_agent25)).length;
  const analyzedCount = taSignals.filter((s: any) => s.execution_data?._has_agent25).length;
  const goCount = taSignals.filter((s: any) => s.execution_data?.technical_analysis_data?.agent_3_handoff?.technical_go_no_go === "GO").length;

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

  return (
    <div className="p-5 space-y-5" data-ocid="technical-analysis.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <LineChart size={16} className="text-cyan-500" />
          <span className="font-mono text-[12px] font-bold text-foreground uppercase tracking-widest">
            Agent 2.5: Technical Analysis
          </span>
          <Badge variant="outline" className="font-mono text-[9px] px-1.5 py-0 h-4 border-cyan-500/30 text-cyan-400 bg-cyan-500/5 ml-2">
            INDICATORS & OHLCV
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
            onClick={triggerTA}
            disabled={runningTA}
            className="font-mono text-[10px] h-6 bg-cyan-600 text-white hover:bg-cyan-700 shadow-[0_0_15px_rgba(6,182,212,0.3)]"
          >
            {runningTA ? (
              <><RefreshCw size={10} className="mr-1 animate-spin" /> Analyzing...</>
            ) : (
              <><BarChart2 size={10} className="mr-1" /> Run Technical Analysis</>
            )}
          </Button>
        </div>
      </div>

      <div className="bg-cyan-500/5 border border-cyan-500/20 rounded-lg p-4 mb-4">
        <p className="text-xs text-muted-foreground leading-relaxed">
          <strong>How it works:</strong> Agent 2.5 receives structurally confirmed signals from Agent 2, builds real-time TA-Lib indicators, and evaluates the exact setup. It acts as a strict gating layer: only setups marked as <strong className="text-emerald-400">GO</strong> are passed to Agent 3 for execution sizing.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "PENDING", count: pendingCount, icon: <Clock size={16} />, color: "text-blue-400", bg: "bg-blue-500/5 border-blue-500/20" },
          { label: "ANALYZED", count: analyzedCount, icon: <Activity size={16} />, color: "text-cyan-400", bg: "bg-cyan-500/5 border-cyan-500/20" },
          { label: "HANDOFF: GO", count: goCount, icon: <CheckCircle2 size={16} />, color: "text-emerald-400", bg: "bg-emerald-500/5 border-emerald-500/20" },
          { label: "HANDOFF: WAIT", count: analyzedCount - goCount, icon: <Minus size={16} />, color: "text-amber-400", bg: "bg-amber-500/5 border-amber-500/20" },
        ].map((item) => (
          <div
            key={item.label}
            className={cn("border rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-all hover:scale-[1.02]", item.bg)}
            onClick={() => setFilter(filter === item.label.split(': ')[1] || filter === item.label ? "ALL" : (item.label.split(': ')[1] || item.label))}
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
          {["ALL", "PENDING", "ANALYZED", "GO", "WAIT/NO_GO"].map((s) => (
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
              {s}
            </Badge>
          ))}
        </div>

        <span className="font-mono text-[9px] text-muted-foreground">
          Showing {filtered.length} of {taSignals.length} signals
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
          <BarChart2 size={32} className="mx-auto text-muted-foreground opacity-20" />
          <p className="font-mono text-xs text-muted-foreground">No technical data available</p>
          <p className="font-mono text-[10px] text-muted-foreground opacity-50">
            Signals must be confirmed by Agent 2 first.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((sig: any) => {
            const isExpanded = expandedId === sig.id;
            const eData = sig.execution_data || {};
            const hasTA = eData._has_agent25 === true;
            const taData = eData.technical_analysis_data || {};
            const rootTA = taData.technical_analysis || {};
            const overall = rootTA.overall || {};
            const handoff = rootTA.agent_3_handoff || {};
            const bias = overall.technical_bias || "NEUTRAL";
            const goNoGo = handoff.technical_go_no_go || "WAIT";

            return (
              <div
                key={sig.id}
                className={cn(
                  "bg-card border rounded-lg overflow-hidden transition-all",
                  goNoGo !== "GO" && hasTA ? "opacity-80 border-border" : "border-border"
                )}
              >
                {/* Main Row */}
                <div
                  className="p-4 cursor-pointer hover:bg-secondary/30 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                >
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    {/* Left: Symbol + Direction */}
                    <div className="flex items-center gap-3">
                       <div className="flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary">
                         {directionIcon(bias)}
                       </div>
                      <div>
                        <h3 className="font-bold text-sm text-foreground tracking-tight">{sig.symbol}</h3>
                        <div className={cn("font-mono text-[9px] uppercase tracking-widest font-bold", directionColor(bias))}>
                          {hasTA ? `${bias} (Grade ${overall.technical_grade || '-'})` : "AWAITING TA"}
                        </div>
                      </div>
                      <div className="ml-2 border-l border-border/50 pl-4">
                        {hasTA ? (
                          <Badge variant="outline" className={cn("font-mono text-[9px]", 
                            goNoGo === "GO" ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/5" : "border-amber-500/30 text-amber-400 bg-amber-500/5"
                          )}>
                            {goNoGo === "GO" ? <Navigation size={10} className="mr-1"/> : <Clock size={10} className="mr-1"/>}
                            {goNoGo}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="font-mono text-[9px] border-blue-500/30 text-blue-400 bg-blue-500/5">
                            PENDING TA
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* Right: TA Summary */}
                    {hasTA && (
                       <div className="flex items-center gap-4 hidden md:flex text-right">
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Readiness</div>
                             <div className="font-mono text-xs font-bold text-foreground">
                                {overall.trade_readiness || "—"}
                             </div>
                          </div>
                          <div>
                             <div className="font-mono text-[8px] text-muted-foreground uppercase">Indicators</div>
                             <div className="font-mono text-xs font-bold text-cyan-400">
                                {eData.indicators_computed?.length || 0}
                             </div>
                          </div>
                       </div>
                    )}
                    
                    <div className="text-muted-foreground">
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>

                  {/* Summary (always visible) */}
                  {hasTA && handoff.go_no_go_reason && (
                    <p className="text-xs text-muted-foreground mt-2 pl-11 leading-relaxed line-clamp-1 italic">
                      {handoff.go_no_go_reason}
                    </p>
                  )}
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
                    {hasTA ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pb-4 border-b border-border/30">
                          <div className={cn("bg-background/50 rounded p-3 border border-l-2", goNoGo === "GO" ? "border-emerald-500/30 border-l-emerald-500" : "border-amber-500/30 border-l-amber-500")}>
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Agent 3 Handoff</div>
                            <div className={cn("font-mono text-sm font-bold", goNoGo === "GO" ? "text-emerald-400" : "text-amber-400")}>
                              {goNoGo}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Overall Bias</div>
                            <div className={cn("font-mono text-sm font-bold", directionColor(bias))}>
                              {bias}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Grade & Confidence</div>
                            <div className="font-mono text-sm font-bold text-foreground">
                              {overall.technical_grade || "—"} / {overall.confidence || "—"}
                            </div>
                          </div>
                          <div className="bg-background/50 rounded p-3 border border-border/50">
                            <div className="font-mono text-[8px] text-muted-foreground uppercase">Candles Analyzed</div>
                            <div className="font-mono text-sm font-bold text-cyan-400">
                              {eData.candle_count || "—"}
                            </div>
                          </div>
                        </div>

                        {/* Handoff Reason & Agent 3 Info */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                          <div className={cn("p-3 rounded border shadow-sm border-l-2", goNoGo === "GO" ? "bg-emerald-500/5 border-emerald-500/20 border-l-emerald-500" : "bg-amber-500/5 border-amber-500/20 border-l-amber-500")}>
                            <div className="font-mono text-[9px] uppercase tracking-widest font-semibold mb-1 opacity-80">Handoff Rationale</div>
                            <p className="text-xs text-foreground leading-relaxed mb-3">{handoff.go_no_go_reason}</p>
                            
                            {handoff.must_confirm_before_entry && handoff.must_confirm_before_entry.length > 0 && (
                                <div className="mt-2">
                                  <div className="font-mono text-[9px] text-amber-400 uppercase tracking-widest font-semibold mb-1">Must Confirm Before Entry</div>
                                  <ul className="space-y-1">
                                    {handoff.must_confirm_before_entry.map((c: string, i: number) => (
                                      <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                        <Clock size={10} className="text-amber-400 mt-0.5 shrink-0" />
                                        {c}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                            )}
                          </div>
                          
                          <div className="p-3 rounded border border-border/50 bg-background/50 shadow-sm border-l-2 border-l-zinc-500">
                             <div className="font-mono text-[9px] uppercase tracking-widest font-semibold mb-1 opacity-80">Technical Reasoning</div>
                             <div className="space-y-2 mt-2">
                               {overall.reasoning?.why_this_bias && (
                                 <div>
                                   <span className="text-[10px] font-mono uppercase text-muted-foreground mr-1">Bias:</span>
                                   <span className="text-[11px]">{overall.reasoning.why_this_bias}</span>
                                 </div>
                               )}
                               {overall.reasoning?.why_this_grade && (
                                 <div>
                                   <span className="text-[10px] font-mono uppercase text-muted-foreground mr-1">Grade:</span>
                                   <span className="text-[11px]">{overall.reasoning.why_this_grade}</span>
                                 </div>
                               )}
                             </div>
                             
                             {overall.reasoning?.key_evidence && overall.reasoning.key_evidence.length > 0 && (
                               <div className="mt-3">
                                  <div className="font-mono text-[9px] text-emerald-400 uppercase tracking-widest font-semibold mb-1">Key Evidence</div>
                                  <ul className="space-y-1">
                                    {overall.reasoning.key_evidence.map((ev: string, i: number) => (
                                      <li key={i} className="text-[11px] text-muted-foreground flex items-start gap-1.5">
                                        <CheckCircle2 size={10} className="text-emerald-400 mt-0.5 shrink-0" />
                                        {ev}
                                      </li>
                                    ))}
                                  </ul>
                               </div>
                             )}
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {/* Trend Analysis */}
                          {rootTA.trend_analysis && (
                            <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 border-l-2 border-l-cyan-500 shadow-sm">
                              <div className="font-mono text-[9px] text-cyan-400 uppercase tracking-widest font-semibold mb-1">Trend & Momentum</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Short Term:</strong> {rootTA.trend_analysis.short_term}</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Momentum:</strong> {rootTA.trend_analysis.momentum}</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Strength:</strong> {rootTA.trend_analysis.strength}</div>
                            </div>
                          )}

                          {/* Support/Resistance */}
                          {rootTA.support_resistance_context && (
                            <div className="space-y-1 bg-background/50 p-3 rounded border border-border/50 border-l-2 border-l-blue-500 shadow-sm">
                              <div className="font-mono text-[9px] text-blue-400 uppercase tracking-widest font-semibold mb-1">Support & Resistance</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Nearest Support:</strong> {rootTA.support_resistance_context.nearest_support}</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Nearest Resistance:</strong> {rootTA.support_resistance_context.nearest_resistance}</div>
                              <div className="text-[11px] text-muted-foreground"><strong>Rejection Risk:</strong> {rootTA.support_resistance_context.risk_of_rejection}</div>
                            </div>
                          )}
                        </div>

                        {/* Indicators Built */}
                        {eData.indicators_computed && eData.indicators_computed.length > 0 && (
                          <div className="bg-secondary/50 rounded p-3 border border-border/50 mt-2">
                             <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest font-semibold mb-2">Indicators Computed by TA-Lib</div>
                             <div className="flex flex-wrap gap-2">
                               {eData.indicators_computed.map((ind: string) => (
                                 <Badge key={ind} variant="outline" className="font-mono text-[8px] bg-background">
                                   {ind}
                                 </Badge>
                               ))}
                             </div>
                          </div>
                        )}

                        {/* Source Meta */}
                        <div className="flex items-center gap-4 pt-2 border-t border-border/30 text-[9px] font-mono text-muted-foreground">
                          {eData.analyzed_at && <span>Analyzed: {new Date(eData.analyzed_at).toLocaleTimeString()}</span>}
                        </div>
                      </div>
                    ) : (
                      <div className="bg-background/50 rounded p-4 border border-border/50 text-center">
                         <Clock size={20} className="mx-auto text-muted-foreground opacity-50 mb-2" />
                         <p className="font-mono text-xs text-muted-foreground">Waiting for Agent 2.5 Analysis...</p>
                         <p className="text-[10px] text-muted-foreground opacity-60 mt-1">This confirmed signal needs to be evaluated with TA-Lib indicators.</p>
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
        -- AGENT 2.5 . TECHNICAL ANALYSIS . INDICATOR VALIDATION --
      </div>
    </div>
  );
}
