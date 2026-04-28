import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api } from "@/backend";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { 
  Activity, 
  TrendingUp, 
  RefreshCw,
  Globe
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/opportunities")({
  component: OpportunitiesPage,
});

function OpportunitiesPage() {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await api.getStocksGroupedAnalysis();
      setData(res);
    } catch (err) {
      console.error("Failed to load opportunities", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);
  
  // Format volume
  const formatVolume = (val: number | null) => {
    if (val === null || val === undefined) return "—";
    if (val >= 10000000) return (val / 10000000).toFixed(2) + "Cr";
    if (val >= 100000) return (val / 100000).toFixed(2) + "L";
    if (val >= 1000) return (val / 1000).toFixed(2) + "K";
    return val.toString();
  };

  const formatNumber = (val: number | null) => {
    if (val === null || val === undefined) return "—";
    return val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto" data-ocid="opportunities.page">
      {/* Header Bar */}
      <div className="flex items-center justify-between flex-wrap gap-4 animate-fade-up" data-ocid="opportunities.status_bar">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-emerald-500/15 text-emerald-400">
              <TrendingUp size={20} />
            </div>
            <div>
              <h2 className="font-display text-xl font-bold text-foreground tracking-tight">
                Live Opportunities
              </h2>
              <p className="text-[12px] text-muted-foreground">
                Real-time market scanner results with sentiment-grouped stock candidates
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-[11px] px-3 py-1 border-border text-muted-foreground rounded-full">
            {!loading ? data.length : "—"} Symbols
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={loading}
            className="text-[12px] h-8 border-border rounded-lg"
          >
            <RefreshCw size={13} className={cn("mr-1.5", loading && 'animate-spin')} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Content Section */}
      <div className="space-y-3 animate-fade-up stagger-1">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-primary" />
          <span className="section-label">
            Analyzed Candidates
          </span>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="bg-card border border-border rounded p-4 space-y-3">
                <div className="flex justify-between">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-4 w-16" />
                </div>
                <Skeleton className="h-6 w-24" />
                <div className="space-y-2">
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-full" />
                </div>
              </div>
            ))}
          </div>
        ) : data.length === 0 ? (
          <div className="bg-card border border-border rounded p-10 text-center space-y-3">
            <Globe size={28} className="mx-auto text-muted-foreground opacity-25" />
            <div>
              <p className="font-mono text-xs text-muted-foreground">No opportunities discovered</p>
              <p className="font-mono text-[10px] text-muted-foreground opacity-50 mt-1">
                News grouping has not identified actionable symbols yet.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {data.map((stock, i) => {
              if (stock.error) return null;
              
              const prevClose = stock.last_close || 0;
              const currentPriceCalc = prevClose + (stock.current_change_amount || 0);
              
              const isPositive = (stock.current_change_pct || 0) >= 0;
              const isGapUp = (stock.gap_percentage || 0) >= 0;

              return (
                <div 
                  key={stock.symbol || i} 
                  className="bg-card border border-border rounded p-4 relative overflow-hidden flex flex-col"
                >
                  {/* Symbol & Gap Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-bold text-sm tracking-tight text-foreground">{stock.symbol}</h3>
                      <div className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest mt-0.5">
                        NSE_EQ
                      </div>
                    </div>
                    {stock.gap_percentage !== null && (
                      <Badge 
                        variant="outline" 
                        className={cn(
                          "font-mono text-[9px] px-1.5 py-0 h-4 uppercase tracking-wider",
                          isGapUp 
                            ? "border-chart-1/30 text-chart-1 bg-chart-1/5" 
                            : "border-chart-2/30 text-chart-2 bg-chart-2/5"
                        )}
                      >
                        GAP {isGapUp ? 'UP' : 'DN'} {Math.abs(stock.gap_percentage).toFixed(2)}%
                      </Badge>
                    )}
                  </div>

                  {/* Price Row */}
                  <div className="flex items-baseline gap-2 mb-4">
                    <span className="text-lg font-mono font-semibold tabular-nums text-foreground">
                      {formatNumber(currentPriceCalc)}
                    </span>
                    <span className={cn(
                      "font-mono text-[10px] flex items-center",
                      isPositive ? "text-chart-1" : "text-chart-2"
                    )}>
                      {isPositive ? '+' : '-'}{Math.abs(stock.current_change_pct || 0).toFixed(2)}%
                    </span>
                  </div>

                  {/* Range Bar */}
                  <div className="space-y-1.5 mb-4">
                    <div className="flex justify-between font-mono text-[9px] text-muted-foreground">
                      <span>L: {formatNumber(stock.today_low)}</span>
                      <span>H: {formatNumber(stock.today_high)}</span>
                    </div>
                    <div className="h-1 w-full bg-secondary rounded-full overflow-hidden relative">
                      {(() => {
                        const range = (stock.today_high || 0) - (stock.today_low || 0);
                        const pos = range > 0 ? ((currentPriceCalc - (stock.today_low || 0)) / range) * 100 : 50;
                        return (
                          <>
                            <div 
                              className={cn(
                                "absolute top-0 h-full",
                                isPositive ? "bg-chart-1/70" : "bg-chart-2/70"
                              )}
                              style={{ left: 0, width: `${Math.max(0, Math.min(100, pos))}%` }}
                            />
                            <div 
                              className="absolute top-0 w-[2px] h-full bg-foreground"
                              style={{ left: `calc(${Math.max(0, Math.min(100, pos))}% - 1px)` }}
                            />
                          </>
                        );
                      })()}
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 gap-y-3 gap-x-2 pt-3 border-t border-border/40 mt-auto">
                    <div>
                      <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest mb-0.5">Volume</div>
                      <div className="font-mono text-[11px] text-foreground">{formatVolume(stock.current_volume)}</div>
                    </div>
                    <div>
                      <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest mb-0.5">Prev Close</div>
                      <div className="font-mono text-[11px] text-foreground">{formatNumber(stock.last_close)}</div>
                    </div>
                    <div>
                      <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest mb-0.5">Open</div>
                      <div className="font-mono text-[11px] text-foreground">{formatNumber(stock.today_open)}</div>
                    </div>
                    <div>
                      <div className="font-mono text-[8px] text-muted-foreground uppercase tracking-widest mb-0.5">52W Range</div>
                      <div className="font-mono text-[10px] text-muted-foreground">
                        <span className="text-foreground">{formatNumber(stock["52_week_low"])}</span> - <span className="text-foreground">{formatNumber(stock["52_week_high"])}</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Terminal footer */}
      <div className="font-mono text-[9px] text-muted-foreground opacity-25 text-center tracking-widest pb-1 border-t border-border/20 pt-3 mt-6">
        ── OPPORTUNITIES · EVENT ENGINE PHASE 2 · MARKET SCANNER ACTIVE ──
      </div>
    </div>
  );
}
