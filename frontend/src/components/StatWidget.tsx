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
  default: "border-border text-muted-foreground bg-muted/20",
  amber: "border-amber-500/40 text-amber-400 bg-amber-500/10",
  green: "border-emerald-500/40 text-emerald-400 bg-emerald-500/10",
  red: "border-red-500/40 text-red-400 bg-red-500/10",
  muted: "border-border text-muted-foreground/60 bg-muted/10",
  phase: "border-violet-500/40 text-violet-400 bg-violet-500/10",
};

const TREND_STYLES = {
  up: "text-emerald-400",
  down: "text-red-400",
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
        "relative flex flex-col gap-2.5 p-5 rounded-xl border transition-all duration-300 overflow-hidden group hover:shadow-lg",
        highlight
          ? "bg-primary/5 border-primary/25 shadow-[0_0_20px_oklch(var(--primary)/0.08)]"
          : "bg-card border-border hover:border-primary/20",
      )}
      data-ocid={ocid ?? "stat_widget"}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={cn(
            "flex items-center justify-center w-8 h-8 rounded-lg transition-colors",
            highlight ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary",
          )}>
            <Icon size={16} />
          </div>
          <span className="text-[12px] font-medium uppercase tracking-wider text-muted-foreground truncate">
            {label}
          </span>
        </div>
        {badgeText && (
          <span
            className={cn(
              "font-mono text-[10px] font-semibold px-2 py-0.5 rounded-full border uppercase tracking-wider shrink-0",
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
            "font-display text-3xl font-bold leading-none tabular-nums tracking-tight",
            highlight ? "text-primary" : "text-foreground",
          )}
        >
          {value}
        </span>
        {trend && (
          <span
            className={cn(
              "font-mono text-sm font-bold pb-0.5",
              TREND_STYLES[trend],
            )}
          >
            {TREND_GLYPHS[trend]}
          </span>
        )}
      </div>

      {/* Subtext */}
      {subtext && (
        <div className="text-[12px] text-muted-foreground/70 leading-tight">
          {subtext}
        </div>
      )}

      {/* Decorative left bar if highlight */}
      {highlight && (
        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b from-primary to-primary/40 rounded-r" />
      )}
    </div>
  );
}
