import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { msToDate, formatTimestamp } from "@/types/trading";
import type { ProcessingState, SystemConfig } from "@/types/trading";
import { Activity, Wifi, WifiOff, Clock, Database, Cpu } from "lucide-react";

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
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      {pulse && active && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
      )}
      <span
        className={cn(
          "relative inline-flex rounded-full h-2.5 w-2.5",
          active ? "bg-emerald-400" : "bg-muted-foreground/30",
        )}
      />
    </span>
  );
}

function InfoRow({
  label,
  value,
  icon: Icon,
  highlight = false,
}: {
  label: string;
  value: string;
  icon?: React.ElementType;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-border/30 last:border-0">
      <div className="flex items-center gap-2">
        {Icon && <Icon size={13} className="text-muted-foreground/50" />}
        <span className="text-[12px] text-muted-foreground">
          {label}
        </span>
      </div>
      <span
        className={cn(
          "text-[12px] font-medium text-right truncate max-w-[160px] font-mono",
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
      <div className="bg-card border border-border rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-muted-foreground" />
            <span className="text-[12px] font-semibold text-foreground">
              System Health
            </span>
          </div>
          {/* Endpoint badge */}
          <Badge
            variant="outline"
            className={cn(
              "text-[10px] font-mono font-semibold px-2.5 py-0.5 rounded-full uppercase tracking-wider",
              "border-emerald-500/40 text-emerald-400 bg-emerald-500/10",
            )}
            data-ocid="system_health_panel.endpoint_status"
          >
            <StatusDot active={true} />
            <span className="ml-1.5">Connected</span>
          </Badge>
        </div>

        <div className="space-y-0">
          <InfoRow
            label="Last Poll"
            value={
              lastPollTs > 0 ? `${lastPollDate} ${lastPollStr} UTC` : "Never"
            }
            icon={Clock}
          />
          <InfoRow
            label="Queue"
            value={`${queue} articles`}
            icon={Database}
            highlight={queue > 0}
          />
          <InfoRow
            label="Processed"
            value={`${totalProcessed.toLocaleString()} total`}
            icon={Cpu}
          />
          <InfoRow label="Mode" value={processingState?.current_mode ?? "—"} />
        </div>

        {/* Polling indicator */}
        <div className={cn(
          "flex items-center gap-2.5 p-2.5 rounded-lg border transition-all",
          isPolling
            ? "bg-emerald-500/5 border-emerald-500/20"
            : "bg-secondary/30 border-border/50",
        )}>
          <StatusDot active={isPolling} pulse />
          {isPolling ? (
            <Wifi size={14} className="text-emerald-400" />
          ) : (
            <WifiOff size={14} className="text-muted-foreground/50" />
          )}
          <span
            className={cn(
              "text-[12px] font-medium",
              isPolling ? "text-emerald-400" : "text-muted-foreground/60",
            )}
          >
            {isPolling ? "Auto-Polling Active" : "Polling Inactive"}
          </span>
          {isPolling && config && (
            <span className="font-mono text-[11px] text-muted-foreground ml-auto">
              every {config.polling_interval_mins}m
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
