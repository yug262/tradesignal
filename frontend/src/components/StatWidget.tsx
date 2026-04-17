import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

type BadgeVariant = "default" | "amber" | "green" | "red" | "muted" | "phase";

interface StatWidgetProps {
  label: string;
  value: string;
  icon: LucideIcon;
  subtext?: string;
  trend?: "up" | "down" | "neutral";
  badgeText?: string;
  badgeVariant?: BadgeVariant;
  highlight?: boolean;
  ocid?: string;
}

const BADGE_STYLES: Record<BadgeVariant, string> = {
  default: "border-border text-muted-foreground bg-secondary",
  amber: "border-primary/40 text-primary bg-primary/10",
  green: "border-chart-1/40 text-chart-1 bg-chart-1/10",
  red: "border-destructive/40 text-destructive bg-destructive/10",
  muted: "border-border text-muted-foreground opacity-50",
  phase: "border-chart-4/40 text-chart-4 bg-chart-4/10",
};

const TREND_STYLES = {
  up: "text-chart-1",
  down: "text-destructive",
  neutral: "text-muted-foreground",
};

const TREND_GLYPHS = {
  up: "▲",
  down: "▼",
  neutral: "—",
};

export function StatWidget({
  label,
  value,
  icon: Icon,
  subtext,
  trend,
  badgeText,
  badgeVariant = "default",
  highlight = false,
  ocid,
}: StatWidgetProps) {
  return (
    <div
      className={cn(
        "relative flex flex-col gap-2 p-4 rounded border transition-smooth overflow-hidden",
        highlight
          ? "bg-primary/5 border-primary/25 shadow-[0_0_20px_oklch(var(--primary)/0.06)]"
          : "bg-card border-border",
      )}
      data-ocid={ocid ?? "stat_widget"}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon
            size={12}
            className={highlight ? "text-primary" : "text-muted-foreground"}
          />
          <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground truncate">
            {label}
          </span>
        </div>
        {badgeText && (
          <span
            className={cn(
              "font-mono text-[9px] px-1.5 py-0.5 rounded border uppercase tracking-wider shrink-0",
              BADGE_STYLES[badgeVariant],
            )}
          >
            {badgeText}
          </span>
        )}
      </div>

      {/* Value */}
      <div className="flex items-end gap-2">
        <span
          className={cn(
            "font-display text-2xl font-bold leading-none tabular-nums",
            highlight ? "text-primary" : "text-foreground",
          )}
        >
          {value}
        </span>
        {trend && (
          <span
            className={cn(
              "font-mono text-[11px] font-bold pb-0.5",
              TREND_STYLES[trend],
            )}
          >
            {TREND_GLYPHS[trend]}
          </span>
        )}
      </div>

      {/* Subtext */}
      {subtext && (
        <div className="font-mono text-[10px] text-muted-foreground opacity-60 leading-tight">
          {subtext}
        </div>
      )}

      {/* Decorative left bar if highlight */}
      {highlight && (
        <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary/50 rounded-r" />
      )}
    </div>
  );
}
