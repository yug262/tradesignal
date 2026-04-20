import { Button } from "@/components/ui/button";
import {
  useDashboardSummary,
  useProcessingState,
  useTriggerFetch,
} from "@/hooks/useNewsItems";
import { cn } from "@/lib/utils";
import { formatUTC } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { RefreshCw } from "lucide-react";

export function AppHeader() {
  const activePageTitle = useUIStore((s) => s.activePageTitle);
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
      className="flex items-center gap-4 h-12 px-4 bg-card border-b border-border shrink-0"
      data-ocid="header"
    >
      {/* Page title */}
      <div className="flex items-center gap-2 min-w-0">
        <h1
          className="font-display text-sm font-semibold text-foreground truncate"
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
            "flex items-center gap-1.5 px-2.5 py-1 rounded font-mono text-[10px] tracking-widest uppercase border",
            isLive
              ? "bg-primary/10 border-primary/30 text-primary"
              : "bg-secondary border-border text-muted-foreground",
          )}
          data-ocid="header.system_mode"
        >
          {isLive && (
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary" />
            </span>
          )}
          [ {systemMode.toUpperCase()} ]
        </div>

        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded font-mono text-[10px] tracking-wider uppercase border bg-chart-1/10 border-chart-1/30 text-chart-1"
          data-ocid="header.endpoint_status"
        >
          <span className="inline-flex rounded-full h-1.5 w-1.5 bg-chart-1" />
          LIVE ENDPOINT
        </div>
      </div>

      {/* Right — refresh + polling */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Last refresh */}
        <span
          className="font-mono text-[11px] text-muted-foreground hidden md:block"
          data-ocid="header.last_refresh"
        >
          {lastRefresh === "Never" ? "Never" : `${lastRefresh} UTC`}
        </span>

        {/* Polling indicator */}
        <div
          className={cn(
            "flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider",
            isPolling ? "text-chart-1" : "text-muted-foreground",
          )}
          title={isPolling ? "Polling active" : "Polling inactive"}
          data-ocid="header.polling_status"
        >
          {isPolling ? (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-chart-1 opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-chart-1" />
            </span>
          ) : (
            <span className="inline-flex rounded-full h-2 w-2 bg-muted" />
          )}
          <span className="hidden lg:inline">
            {isPolling ? "LIVE" : "IDLE"}
          </span>
        </div>

        {/* Manual refresh */}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          onClick={handleRefresh}
          disabled={triggerFetch.isPending}
          aria-label="Trigger manual refresh"
          data-ocid="header.refresh_button"
        >
          <RefreshCw
            size={13}
            className={cn(triggerFetch.isPending && "animate-spin")}
          />
        </Button>
      </div>
    </header>
  );
}
