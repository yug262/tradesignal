import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  BookOpen,
  Brain,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Globe,
  LayoutDashboard,
  LayoutGrid,
  Newspaper,
  Settings,
  Terminal,
  TrendingUp,
} from "lucide-react";

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
  phase?: number;
}

const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Dashboard", icon: <LayoutDashboard size={16} /> },
  {
    path: "/opportunities",
    label: "Opportunities",
    icon: <TrendingUp size={16} />,
    phase: 2,
  },
  {
    path: "/agent-signals",
    label: "Trade Signal (A1)",
    icon: <Brain size={16} />,
  },
  {
    path: "/market-open",
    label: "Market Open (A2)",
    icon: <TrendingUp size={16} />,
  },
  {
    path: "/execution-planner",
    label: "Execution Planner (A3)",
    icon: <ClipboardList size={16} />,
  },
  {
    path: "/paper-trading",
    label: "Paper Trading",
    icon: <TrendingUp size={16} />,
  },
  { path: "/news-feed", label: "News Feed", icon: <Newspaper size={16} /> },
  {
    path: "/grouping",
    label: "Stock Grouping",
    icon: <LayoutGrid size={16} />,
  },
  {
    path: "/mode-analysis",
    label: "Mode Analysis",
    icon: <BarChart3 size={16} />,
    phase: 3,
  },
  {
    path: "/trade-planner",
    label: "Trade Planner",
    icon: <ClipboardList size={16} />,
    phase: 4,
  },
  {
    path: "/journal",
    label: "Journal",
    icon: <BookOpen size={16} />,
    phase: 6,
  },
  {
    path: "/market-regime",
    label: "Market Regime",
    icon: <Globe size={16} />,
    phase: 2,
  },
];

const BOTTOM_ITEMS: NavItem[] = [
  { path: "/settings", label: "Settings", icon: <Settings size={16} /> },
];

export function AppSidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  function isActive(path: string) {
    if (path === "/") return currentPath === "/";
    return currentPath.startsWith(path);
  }

  return (
    <aside
      className={cn(
        "relative flex flex-col h-screen bg-card border-r border-border transition-all duration-200 shrink-0 z-20",
        collapsed ? "w-[60px]" : "w-[240px]",
      )}
      data-ocid="sidebar"
    >
      {/* Logo */}
      <div
        className={cn(
          "flex items-center gap-2.5 px-3 py-4 border-b border-border",
          collapsed && "justify-center px-0",
        )}
      >
        <div className="flex items-center justify-center w-7 h-7 rounded bg-primary/20 border border-primary/40 shrink-0">
          <Terminal size={13} className="text-primary" />
        </div>
        {!collapsed && (
          <div className="flex flex-col min-w-0">
            <span className="font-display text-sm font-semibold tracking-wider text-foreground truncate">
              TradeSignal
            </span>
            <span className="font-mono text-[9px] text-muted-foreground tracking-widest uppercase">
              Intelligence
            </span>
          </div>
        )}
      </div>

      {/* Main nav */}
      <nav
        className="flex-1 flex flex-col gap-0.5 px-1.5 py-2 overflow-y-auto"
        data-ocid="sidebar.nav"
      >
        {NAV_ITEMS.map((item) => (
          <SidebarLink
            key={item.path}
            item={item}
            collapsed={collapsed}
            active={isActive(item.path)}
          />
        ))}
      </nav>

      <Separator className="mx-2 opacity-30" />

      {/* Bottom nav */}
      <nav className="flex flex-col gap-0.5 px-1.5 py-2">
        {BOTTOM_ITEMS.map((item) => (
          <SidebarLink
            key={item.path}
            item={item}
            collapsed={collapsed}
            active={isActive(item.path)}
          />
        ))}
      </nav>

      {/* Version badge */}
      {!collapsed && (
        <div className="px-3 pb-3">
          <div className="font-mono text-[9px] text-muted-foreground tracking-widest uppercase opacity-50">
            v1.0.0 · Phase 1
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={toggleSidebar}
        className="absolute -right-3 top-16 flex items-center justify-center w-6 h-6 rounded-full bg-card border border-border text-muted-foreground hover:text-foreground hover:border-primary/40 transition-smooth z-30"
        type="button"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        data-ocid="sidebar.toggle"
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </aside>
  );
}

function SidebarLink({
  item,
  collapsed,
  active,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}) {
  return (
    <Link
      to={item.path}
      className={cn(
        "group relative flex items-center gap-2.5 rounded px-2 py-2 transition-smooth",
        "text-muted-foreground hover:text-foreground hover:bg-secondary",
        active && "bg-primary/10 text-primary border border-primary/20",
        collapsed && "justify-center px-0",
      )}
      data-ocid={`sidebar.nav.${item.label.toLowerCase().replace(/\s+/g, "_")}`}
      title={collapsed ? item.label : undefined}
    >
      <span className={cn("shrink-0", active && "text-primary")}>
        {item.icon}
      </span>

      {!collapsed && (
        <>
          <span className="flex-1 text-xs font-medium truncate">
            {item.label}
          </span>
          {item.phase && item.phase > 1 && (
            <Badge
              variant="outline"
              className="text-[9px] px-1 py-0 h-4 font-mono border-border text-muted-foreground opacity-60 shrink-0"
            >
              P{item.phase}
            </Badge>
          )}
        </>
      )}

      {/* Active indicator */}
      {active && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-primary rounded-r" />
      )}
    </Link>
  );
}
