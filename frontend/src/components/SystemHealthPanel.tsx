import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { msToDate, formatTimestamp } from "@/types/trading";
import type { ProcessingState, SystemConfig } from "@/types/trading";
import { Activity, Globe, RefreshCw } from "lucide-react";

interface SystemHealthPanelProps {
  processingState: ProcessingState | null | undefined;
  config: SystemConfig | null | undefined;
  onFetchNow?: () => void;
  isFetching?: boolean;
}

function StatusDot({
  active,
  pulse = false,
}: { active: boolean; pulse?: boolean }) {
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      {pulse && active && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-chart-1 opacity-60" />
      )}
      <span
        className={cn(
          "relative inline-flex rounded-full h-2 w-2",
          active ? "bg-chart-1" : "bg-muted-foreground opacity-40",
        )}
      />
    </span>
  );
}

function InfoRow({
  label,
  value,
  mono = true,
  highlight = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 border-b border-border/30 last:border-0">
      <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest shrink-0">
        {label}
      </span>
      <span
        className={cn(
          "text-[11px] text-right truncate max-w-[160px]",
          mono ? "font-mono" : "font-medium",
          highlight ? "text-primary" : "text-foreground",
        )}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}

export function SystemHealthPanel({
  processingState,
  config,
  onFetchNow,
  isFetching = false,
}: SystemHealthPanelProps) {
  const isPolling = processingState?.is_polling_active ?? false;
  const isLive = true;

  const lastPollTs = processingState?.last_poll_timestamp ?? 0;
  const lastPollStr = lastPollTs > 0 ? formatTimestamp(lastPollTs) : "—";

  const lastPollDate =
    lastPollTs > 0
      ? msToDate(lastPollTs).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        })
      : "";

  const queue = processingState ? processingState.articles_in_queue : 0;
  const totalProcessed = processingState
    ? processingState.total_articles_processed
    : 0;

  return (
    <div className="space-y-3" data-ocid="system_health_panel">
      {/* Endpoint status section */}
      <div className="bg-card border border-border rounded p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Activity size={10} className="text-muted-foreground" />
            <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
              System Health
            </span>
          </div>
          {/* Endpoint badge */}
          <Badge
            variant="outline"
            className={cn(
              "font-mono text-[9px] px-1.5 py-0 h-4 uppercase",
              isLive
                ? "border-chart-1/40 text-chart-1 bg-chart-1/10"
                : "border-chart-4/40 text-chart-4 bg-chart-4/10",
            )}
            data-ocid="system_health_panel.endpoint_status"
          >
            <StatusDot active={isLive} />
            <span className="ml-1">
              LIVE ENDPOINT
            </span>
          </Badge>
        </div>

        <div className="space-y-0">
          <InfoRow
            label="Last Poll"
            value={
              lastPollTs > 0 ? `${lastPollDate} ${lastPollStr} UTC` : "Never"
            }
          />
          <InfoRow
            label="Queue"
            value={`${queue} articles`}
            highlight={queue > 0}
          />
          <InfoRow
            label="Processed"
            value={`${totalProcessed.toLocaleString()} total`}
          />
          <InfoRow label="Mode" value={processingState?.current_mode ?? "—"} />
        </div>

        {/* Polling indicator */}
        <div className="flex items-center gap-2 pt-1">
          <StatusDot active={isPolling} pulse />
          <span
            className={cn(
              "font-mono text-[10px] uppercase tracking-wider",
              isPolling ? "text-chart-1" : "text-muted-foreground opacity-50",
            )}
          >
            {isPolling ? "Polling Active" : "Polling Inactive"}
          </span>
          {isPolling && config && (
            <span className="font-mono text-[9px] text-muted-foreground ml-auto opacity-60">
              every {config.polling_interval_mins}m
            </span>
          )}
        </div>
      </div>

      {/* News Endpoint section */}
      <div className="bg-card border border-border rounded p-3 space-y-2.5">
        <div className="flex items-center gap-1.5">
          <Globe size={10} className="text-muted-foreground" />
          <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
            News Endpoint
          </span>
        </div>

        {config ? (
          <>
            <div
              className="font-mono text-[10px] text-muted-foreground bg-background border border-border rounded px-2 py-1.5 truncate"
              title={config.news_endpoint_url}
            >
              {config.news_endpoint_url || "— not configured —"}
            </div>
            <div className="flex items-center justify-between text-[10px]">
              <span className="font-mono text-muted-foreground uppercase tracking-wider text-[9px]">
                Mode:
              </span>
              <Badge
                variant="outline"
                className="font-mono text-[9px] px-1.5 py-0 h-4 border-border text-muted-foreground"
              >
                {config.processing_mode}
              </Badge>
            </div>

            {onFetchNow && (
              <Button
                variant="outline"
                size="sm"
                className="w-full h-7 font-mono text-[10px] border-primary/30 text-primary hover:bg-primary/10 hover:border-primary/50 uppercase tracking-wider"
                onClick={onFetchNow}
                disabled={isFetching}
                type="button"
                data-ocid="system_health_panel.fetch_now_button"
              >
                <RefreshCw
                  size={10}
                  className={cn("mr-1.5", isFetching && "animate-spin")}
                />
                {isFetching ? "Fetching..." : "FETCH NOW"}
              </Button>
            )}
          </>
        ) : (
          <div className="font-mono text-[10px] text-muted-foreground opacity-40 text-center py-2">
            — loading config —
          </div>
        )}
      </div>
    </div>
  );
}
