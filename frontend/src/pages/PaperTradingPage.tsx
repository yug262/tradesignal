import { useEffect, useState, useCallback } from "react";
import { api } from "@/backend";
import type { PaperTradingDashboard, PaperTrade, AgentLog, AnalyticsData } from "@/types/trading";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  ArrowUpRight, ArrowDownRight, RefreshCw, TrendingUp, TrendingDown,
  Wallet, Target, ShieldAlert, Activity, BarChart3, Clock,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";

function fmt(n: number) { return `₹${Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`; }
function fmtPct(n: number) { return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`; }
function fmtTime(ms: number) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("en-IN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit", day: "2-digit", month: "short" });
}
function fmtDuration(ms: number | null) {
  if (!ms) return "—";
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

const CHART_COLORS = ["#22c55e", "#ef4444", "#3b82f6", "#f59e0b", "#8b5cf6", "#06b6d4"];

export function PaperTradingPage() {
  const [dashboard, setDashboard] = useState<PaperTradingDashboard | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [closedTrades, setClosedTrades] = useState<PaperTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  const loadData = useCallback(async () => {
    try {
      const [dash, anal, closed] = await Promise.all([
        api.getPaperTradingDashboard(),
        api.getPaperTradingAnalytics(),
        api.getClosedPositions(100),
      ]);
      setDashboard(dash);
      setAnalytics(anal);
      setClosedTrades(closed.positions);
    } catch (e) { console.error("Load failed:", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); const iv = setInterval(loadData, 15000); return () => clearInterval(iv); }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try { await api.refreshPaperTradePrices(); await loadData(); } catch {}
    setRefreshing(false);
  };

  if (loading) return <div className="flex items-center justify-center h-[60vh]"><div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" /></div>;

  const p = dashboard?.portfolio;

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" /> Paper Trading
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Simulated trades • Real-time monitoring • Full audit trail</p>
        </div>
        <button onClick={handleRefresh} disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-sm font-medium transition-all border border-primary/20">
          <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
          {refreshing ? "Refreshing..." : "Refresh Prices"}
        </button>
      </div>

      {/* Portfolio Summary Cards */}
      {p && <PortfolioCards portfolio={p} />}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="bg-card border border-border">
          <TabsTrigger value="overview">Open Positions</TabsTrigger>
          <TabsTrigger value="closed">Trade History</TabsTrigger>
          <TabsTrigger value="activity">Activity Log</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OpenPositionsTable positions={dashboard?.open_positions || []} onRefresh={loadData} />
        </TabsContent>
        <TabsContent value="closed">
          <ClosedPositionsTable positions={closedTrades} />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityLog logs={dashboard?.recent_activity || []} />
        </TabsContent>
        <TabsContent value="analytics">
          <AnalyticsPanel data={analytics} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/* ═══════════════════ PORTFOLIO CARDS ═══════════════════ */
function PortfolioCards({ portfolio: p }: { portfolio: PaperTradingDashboard["portfolio"] }) {
  const cards = [
    { label: "Total Capital", value: fmt(p.total_capital), icon: <Wallet className="h-4 w-4" />, color: "text-blue-400" },
    { label: "Available Cash", value: fmt(p.available_cash), icon: <Wallet className="h-4 w-4" />, color: "text-cyan-400" },
    { label: "Total P&L", value: `${p.total_pnl >= 0 ? "+" : "-"}${fmt(p.total_pnl)}`, icon: p.total_pnl >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />, color: p.total_pnl >= 0 ? "text-emerald-400" : "text-red-400", sub: fmtPct(p.total_capital > 0 ? (p.total_pnl / p.total_capital) * 100 : 0) },
    { label: "Today's P&L", value: `${p.todays_pnl >= 0 ? "+" : "-"}${fmt(p.todays_pnl)}`, icon: <Activity className="h-4 w-4" />, color: p.todays_pnl >= 0 ? "text-emerald-400" : "text-red-400" },
    { label: "Win Rate", value: `${p.win_rate.toFixed(1)}%`, icon: <Target className="h-4 w-4" />, color: p.win_rate >= 50 ? "text-emerald-400" : "text-amber-400", sub: `${p.winning_trades}W / ${p.losing_trades}L` },
    { label: "Open / Closed", value: `${p.open_trades} / ${p.closed_trades}`, icon: <BarChart3 className="h-4 w-4" />, color: "text-purple-400", sub: `${p.total_trades} total` },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="bg-card border border-border rounded-xl p-4 hover:border-primary/30 transition-all group">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">{c.label}</span>
            <span className={cn("opacity-60 group-hover:opacity-100 transition-opacity", c.color)}>{c.icon}</span>
          </div>
          <div className={cn("text-lg font-bold tracking-tight", c.color)}>{c.value}</div>
          {c.sub && <div className="text-[11px] text-muted-foreground mt-1">{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════ OPEN POSITIONS TABLE ═══════════════════ */
function OpenPositionsTable({ positions, onRefresh }: { positions: PaperTrade[]; onRefresh: () => void }) {
  const handleClose = async (trade: PaperTrade) => {
    if (!trade.current_price) return;
    if (!confirm(`Close ${trade.symbol} at ₹${trade.current_price}?`)) return;
    try { await api.closePaperTrade(trade.id, trade.current_price, "MANUAL_EXIT"); onRefresh(); } catch {}
  };

  if (positions.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-12 text-center">
        <ShieldAlert className="h-10 w-10 text-muted-foreground mx-auto mb-3 opacity-40" />
        <p className="text-muted-foreground font-medium">No open positions</p>
        <p className="text-xs text-muted-foreground mt-1">Trades will appear here when Agent 3 generates BUY signals</p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              {["Symbol", "Action", "Qty", "Entry", "Current", "SL", "Target", "P&L", "P&L %", "Mode", ""].map(h => (
                <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((t) => (
              <tr key={t.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3 font-semibold">{t.symbol}</td>
                <td className="px-4 py-3"><Badge variant={t.action === "BUY" ? "default" : "destructive"} className="text-[10px]">{t.action}</Badge></td>
                <td className="px-4 py-3 font-mono text-xs">{t.quantity}</td>
                <td className="px-4 py-3 font-mono text-xs">{fmt(t.entry_price)}</td>
                <td className="px-4 py-3 font-mono text-xs font-semibold">{t.current_price ? fmt(t.current_price) : "—"}</td>
                <td className="px-4 py-3 font-mono text-xs text-red-400">{fmt(t.stop_loss)}</td>
                <td className="px-4 py-3 font-mono text-xs text-emerald-400">{fmt(t.target_price)}</td>
                <td className={cn("px-4 py-3 font-mono text-xs font-bold", t.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {t.pnl >= 0 ? "+" : ""}{fmt(t.pnl)}
                </td>
                <td className={cn("px-4 py-3 font-mono text-xs", t.pnl_percentage >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {fmtPct(t.pnl_percentage)}
                </td>
                <td className="px-4 py-3"><Badge variant="outline" className="text-[9px]">{t.trade_mode}</Badge></td>
                <td className="px-4 py-3">
                  <button onClick={() => handleClose(t)} className="px-3 py-1 text-[10px] rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 font-medium transition-all">Close</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════ CLOSED POSITIONS TABLE ═══════════════════ */
function ClosedPositionsTable({ positions }: { positions: PaperTrade[] }) {
  if (positions.length === 0) {
    return <div className="bg-card border border-border rounded-xl p-12 text-center"><p className="text-muted-foreground">No closed trades yet</p></div>;
  }
  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              {["Symbol", "Action", "Qty", "Entry", "Exit", "P&L", "P&L %", "Exit Reason", "Duration", "Time"].map(h => (
                <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((t) => (
              <tr key={t.id} className="border-b border-border/50 hover:bg-muted/20 transition-colors">
                <td className="px-4 py-3 font-semibold">{t.symbol}</td>
                <td className="px-4 py-3"><Badge variant={t.action === "BUY" ? "default" : "destructive"} className="text-[10px]">{t.action}</Badge></td>
                <td className="px-4 py-3 font-mono text-xs">{t.quantity}</td>
                <td className="px-4 py-3 font-mono text-xs">{fmt(t.entry_price)}</td>
                <td className="px-4 py-3 font-mono text-xs">{t.exit_price ? fmt(t.exit_price) : "—"}</td>
                <td className={cn("px-4 py-3 font-mono text-xs font-bold", t.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {t.pnl >= 0 ? "+" : ""}{fmt(t.pnl)}
                </td>
                <td className={cn("px-4 py-3 font-mono text-xs", t.pnl_percentage >= 0 ? "text-emerald-400" : "text-red-400")}>{fmtPct(t.pnl_percentage)}</td>
                <td className="px-4 py-3">
                  <Badge variant="outline" className={cn("text-[9px]",
                    t.exit_reason === "TARGET_HIT" && "border-emerald-500/30 text-emerald-400",
                    t.exit_reason === "STOP_LOSS_HIT" && "border-red-500/30 text-red-400",
                  )}>{t.exit_reason || "—"}</Badge>
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground"><Clock className="inline h-3 w-3 mr-1" />{fmtDuration(t.duration_ms)}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{fmtTime(t.exit_time || t.entry_time)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ═══════════════════ ACTIVITY LOG ═══════════════════ */
function ActivityLog({ logs }: { logs: AgentLog[] }) {
  if (logs.length === 0) {
    return <div className="bg-card border border-border rounded-xl p-12 text-center"><p className="text-muted-foreground">No activity yet</p></div>;
  }
  return (
    <div className="bg-card border border-border rounded-xl divide-y divide-border/50">
      {logs.map((l) => (
        <div key={l.id} className="px-4 py-3 flex items-start gap-3 hover:bg-muted/10 transition-colors">
          <div className={cn("mt-1 flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold",
            l.signal?.includes("BUY") ? "bg-emerald-500/20 text-emerald-400" :
            l.signal?.includes("STOP") || l.signal?.includes("LOSS") ? "bg-red-500/20 text-red-400" :
            l.signal?.includes("TARGET") ? "bg-blue-500/20 text-blue-400" :
            "bg-muted text-muted-foreground"
          )}>
            {l.signal?.includes("BUY") ? <ArrowUpRight className="h-3.5 w-3.5" /> :
             l.signal?.includes("STOP") || l.signal?.includes("LOSS") ? <ArrowDownRight className="h-3.5 w-3.5" /> :
             <Activity className="h-3.5 w-3.5" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              {l.symbol && <span className="font-semibold text-sm">{l.symbol}</span>}
              <Badge variant="outline" className="text-[9px] px-1.5">{l.agent_name}</Badge>
              {l.signal && <Badge variant="secondary" className="text-[9px] px-1.5">{l.signal}</Badge>}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">{l.message}</p>
          </div>
          <span className="text-[10px] text-muted-foreground whitespace-nowrap">{fmtTime(l.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

/* ═══════════════════ ANALYTICS PANEL ═══════════════════ */
function AnalyticsPanel({ data }: { data: AnalyticsData | null }) {
  if (!data || data.win_loss.total === 0) {
    return <div className="bg-card border border-border rounded-xl p-12 text-center"><p className="text-muted-foreground">Complete some trades to see analytics</p></div>;
  }
  const pieData = [
    { name: "Wins", value: data.win_loss.wins, color: "#22c55e" },
    { name: "Losses", value: data.win_loss.losses, color: "#ef4444" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Portfolio Growth */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-primary" />Portfolio Growth</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.portfolio_growth}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
              <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
              <Area type="monotone" dataKey="cumulative_pnl" stroke="#3b82f6" fill="#3b82f680" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        {/* Daily P&L */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" />Daily P&L</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.daily_pnl}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
              <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="pnl" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                {data.daily_pnl.map((entry, i) => <Cell key={i} fill={entry.pnl >= 0 ? "#22c55e" : "#ef4444"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        {/* Win/Loss Pie */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><Target className="h-4 w-4 text-primary" />Win / Loss Ratio</h3>
          <div className="flex items-center gap-6">
            <ResponsiveContainer width={160} height={160}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} dataKey="value" strokeWidth={0}>
                  {pieData.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2">
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-emerald-500" /><span className="text-sm">{data.win_loss.wins} Wins</span></div>
              <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full bg-red-500" /><span className="text-sm">{data.win_loss.losses} Losses</span></div>
              <div className="text-xs text-muted-foreground mt-2">Win Rate: {data.win_loss.total > 0 ? ((data.win_loss.wins / data.win_loss.total) * 100).toFixed(1) : 0}%</div>
            </div>
          </div>
        </div>
        {/* Symbol Performance */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" />Symbol Performance</h3>
          <div className="space-y-2 max-h-[180px] overflow-y-auto pr-2">
            {data.symbol_performance.map((s) => (
              <div key={s.symbol} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-muted/20">
                <span className="font-semibold text-sm">{s.symbol}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">{s.trades} trades</span>
                  <span className={cn("font-mono text-xs font-bold", s.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>{s.pnl >= 0 ? "+" : ""}{fmt(s.pnl)}</span>
                </div>
              </div>
            ))}
            {data.symbol_performance.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No data yet</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
