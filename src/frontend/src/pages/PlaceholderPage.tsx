import { Badge } from "@/components/ui/badge";
import {
  Activity,
  BarChart3,
  BookOpen,
  ClipboardList,
  Globe,
  LayoutDashboard,
  type LucideIcon,
  Newspaper,
  TrendingUp,
} from "lucide-react";

const ICON_MAP: Record<string, LucideIcon> = {
  LayoutDashboard,
  TrendingUp,
  Newspaper,
  BarChart3,
  ClipboardList,
  BookOpen,
  Globe,
  Activity,
};

interface PlaceholderPageProps {
  title: string;
  description: string;
  phase: number;
  icon?: string;
}

export function PlaceholderPage({
  title,
  description,
  phase,
  icon = "LayoutDashboard",
}: PlaceholderPageProps) {
  const Icon = ICON_MAP[icon] ?? LayoutDashboard;

  return (
    <div
      className="flex flex-col items-center justify-center min-h-full p-8 text-center"
      data-ocid="placeholder.page"
    >
      <div className="max-w-md w-full">
        {/* Icon */}
        <div className="flex items-center justify-center w-16 h-16 rounded-lg bg-card border border-border mx-auto mb-6">
          <Icon size={28} className="text-muted-foreground" />
        </div>

        {/* Phase badge */}
        <div className="flex justify-center mb-4">
          <Badge
            variant="outline"
            className="font-mono text-[10px] tracking-widest uppercase border-primary/30 text-primary bg-primary/5 px-3 py-1"
            data-ocid="placeholder.phase_badge"
          >
            ▸ Coming in Phase {phase}
          </Badge>
        </div>

        {/* Title */}
        <h2 className="font-display text-xl font-semibold text-foreground mb-3">
          {title}
        </h2>

        {/* Description */}
        <p className="text-sm text-muted-foreground leading-relaxed mb-6">
          {description}
        </p>

        {/* Terminal-style divider */}
        <div className="font-mono text-[11px] text-muted-foreground opacity-30 tracking-widest">
          ──────────────────────────────
        </div>
        <div className="font-mono text-[10px] text-muted-foreground opacity-30 mt-2 tracking-wider">
          PHASE {phase} MODULE NOT YET INITIALIZED
        </div>
      </div>
    </div>
  );
}
