import { Button } from "@/components/ui/button";
import {
  useDashboardSummary,
  useProcessingState,
  useTriggerFetch,
} from "@/hooks/useNewsItems";
import { cn } from "@/lib/utils";
import { formatUTC } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { Moon, RefreshCw, Sun, Wifi, WifiOff } from "lucide-react";

export function AppHeader() {
  const { activePageTitle, theme, toggleTheme } = useUIStore();
  const { data: procState } = useProcessingState();
  const { data: summary } = useDashboardSummary();
  const triggerFetch = useTriggerFetch();

  const isPolling = procState?.is_polling_active ?? false;
  const systemMode =
    summary?.system_mode ?? procState?.current_mode ?? "PRE-MARKET";
  const isLive = systemMode === "LIVE" || systemMode === "live";

  const lastRefresh = summary?.last_refresh
    ? formatUTC(new Date(Number(summary.last_refresh) / 1_000_000))
    : "Never";

  function handleRefresh() {
    triggerFetch.mutate();
  }

  return (
    <header
      className="flex items-center gap-4 h-14 px-5 bg-card/80 backdrop-blur-lg border-b border-border shrink-0 sticky top-0 z-10"
      data-ocid="header"
    >
      {/* Page title */}
      <div className="flex items-center gap-2 min-w-0">
        <h1
          className="font-display text-base font-semibold text-foreground truncate tracking-tight"
          data-ocid="header.page_title"
        >
          {activePageTitle}
        </h1>
      </div>

      {/* Center — mode + endpoint status */}
      <div className="flex-1 flex items-center justify-center gap-3">
        {/* System mode */}
        <div
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full font-mono text-[11px] font-semibold tracking-wider uppercase border transition-all",
            isLive
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 glow-emerald"
              : "bg-secondary border-border text-muted-foreground",
          )}
          data-ocid="header.system_mode"
        >
          {isLive && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
          )}
          {systemMode.toUpperCase()}
        </div>

        {/* Endpoint status */}
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-full font-mono text-[11px] font-semibold tracking-wider uppercase border bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
          data-ocid="header.endpoint_status"
        >
          <span className="inline-flex rounded-full h-2 w-2 bg-emerald-400" />
          Connected
        </div>
      </div>

      {/* Right — refresh + polling */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Last refresh */}
        <span
          className="font-mono text-[11px] text-muted-foreground hidden md:block"
          data-ocid="header.last_refresh"
          title="Last data refresh time"
        >
          {lastRefresh === "Never" ? "Never refreshed" : `${lastRefresh} UTC`}
        </span>

        {/* Polling indicator */}
        <div
          className={cn(
            "flex items-center gap-2 px-2.5 py-1 rounded-full font-mono text-[11px] font-medium uppercase tracking-wider border transition-all",
            isPolling
              ? "text-emerald-400 border-emerald-500/20 bg-emerald-500/5"
              : "text-muted-foreground border-border bg-secondary/50",
          )}
          title={isPolling ? "Auto-polling is active — data refreshes automatically" : "Auto-polling is off — use manual refresh"}
          data-ocid="header.polling_status"
        >
          {isPolling ? (
            <Wifi size={13} className="text-emerald-400" />
          ) : (
            <WifiOff size={13} />
          )}
          <span className="hidden lg:inline">
            {isPolling ? "Auto" : "Manual"}
          </span>
        </div>

        {/* Manual refresh */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg"
          onClick={handleRefresh}
          disabled={triggerFetch.isPending}
          aria-label="Trigger manual refresh"
          title="Fetch latest data from all sources"
          data-ocid="header.refresh_button"
        >
          <RefreshCw
            size={15}
            className={cn(triggerFetch.isPending && "animate-spin")}
          />
        </Button>

        {/* Theme toggle */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-lg"
          onClick={toggleTheme}
          aria-label="Toggle color theme"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          data-ocid="header.theme_toggle"
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </Button>
      </div>
    </header>
  );
}
