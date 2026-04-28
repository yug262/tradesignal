import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  Brain,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  LayoutDashboard,
  LayoutGrid,
  LineChart,
  Newspaper,
  Settings,
  TrendingUp,
  Activity,
  Wallet,
  Zap,
} from "lucide-react";

interface NavItem {
  path: string;
  label: string;
  icon: React.ReactNode;
  badge?: string;
  badgeColor?: string;
  disabled?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: "Overview",
    items: [
      { path: "/", label: "Dashboard", icon: <LayoutDashboard size={18} /> },
    ],
  },
  {
    title: "Trading Pipeline",
    items: [
      {
        path: "/agent-signals",
        label: "Discovery",
        icon: <Brain size={18} />,
        badge: "A1",
        badgeColor: "text-violet-400 border-violet-500/30 bg-violet-500/10",
      },
      {
        path: "/market-open",
        label: "Market Open",
        icon: <Activity size={18} />,
        badge: "A2",
        badgeColor: "text-blue-400 border-blue-500/30 bg-blue-500/10",
      },
      {
        path: "/technical-analysis",
        label: "Tech Analysis",
        icon: <LineChart size={18} />,
        badge: "A2.5",
        badgeColor: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
      },
      {
        path: "/execution-planner",
        label: "Execution",
        icon: <ClipboardList size={18} />,
        badge: "A3",
        badgeColor: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10",
      },
    ],
  },
  {
    title: "Trading",
    items: [
      {
        path: "/paper-trading",
        label: "Paper Trading",
        icon: <Wallet size={18} />,
      },
      {
        path: "/opportunities",
        label: "Opportunities",
        icon: <TrendingUp size={18} />,
      },
    ],
  },
  {
    title: "Data",
    items: [
      {
        path: "/news-feed",
        label: "News Feed",
        icon: <Newspaper size={18} />,
      },
      {
        path: "/grouping",
        label: "Stock Grouping",
        icon: <LayoutGrid size={18} />,
      },
    ],
  },
];

const BOTTOM_ITEMS: NavItem[] = [
  { path: "/settings", label: "Settings", icon: <Settings size={18} /> },
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
        "relative flex flex-col h-screen border-r border-border transition-all duration-300 shrink-0 z-20",
        "bg-sidebar",
        collapsed ? "w-[68px]" : "w-[250px]",
      )}
      data-ocid="sidebar"
    >
      {/* Logo */}
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-5 border-b border-sidebar-border",
          collapsed && "justify-center px-0",
        )}
      >
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-primary/80 to-primary shadow-lg shrink-0">
          <Zap size={16} className="text-primary-foreground" />
        </div>
        {!collapsed && (
          <div className="flex flex-col min-w-0">
            <span className="font-display text-sm font-bold tracking-wide text-foreground truncate">
              TradeSignal
            </span>
            <span className="font-mono text-[10px] text-muted-foreground tracking-wider uppercase">
              AI Trading Intelligence
            </span>
          </div>
        )}
      </div>

      {/* Main nav */}
      <nav
        className="flex-1 flex flex-col gap-1 px-2 py-3 overflow-y-auto"
        data-ocid="sidebar.nav"
      >
        {NAV_SECTIONS.map((section, sectionIdx) => (
          <div key={section.title} className={cn(sectionIdx > 0 && "mt-3")}>
            {/* Section Header */}
            {!collapsed && (
              <div className="px-3 pb-1.5">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground/60">
                  {section.title}
                </span>
              </div>
            )}
            {collapsed && sectionIdx > 0 && (
              <Separator className="mx-3 my-1 opacity-20" />
            )}

            {/* Section Items */}
            <div className="flex flex-col gap-0.5">
              {section.items.map((item) => (
                <SidebarLink
                  key={item.path}
                  item={item}
                  collapsed={collapsed}
                  active={isActive(item.path)}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <Separator className="mx-3 opacity-20" />

      {/* Bottom nav */}
      <nav className="flex flex-col gap-0.5 px-2 py-3">
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
        <div className="px-4 pb-4">
          <div className="font-mono text-[10px] text-muted-foreground/40 tracking-wider">
            v1.0 · Production
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={toggleSidebar}
        className="absolute -right-3.5 top-[72px] flex items-center justify-center w-7 h-7 rounded-full bg-card border border-border shadow-md text-muted-foreground hover:text-foreground hover:border-primary/40 hover:bg-primary/5 transition-all z-30"
        type="button"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        data-ocid="sidebar.toggle"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
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
        "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-200",
        "text-muted-foreground hover:text-foreground hover:bg-secondary/80",
        active &&
          "bg-primary/10 text-primary font-medium shadow-sm",
        collapsed && "justify-center px-0",
        item.disabled && "opacity-40 pointer-events-none",
      )}
      data-ocid={`sidebar.nav.${item.label.toLowerCase().replace(/\s+/g, "_")}`}
      title={collapsed ? item.label : undefined}
    >
      {/* Active indicator */}
      {active && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-primary rounded-r-full" />
      )}

      <span className={cn("shrink-0", active && "text-primary")}>
        {item.icon}
      </span>

      {!collapsed && (
        <>
          <span className="flex-1 text-[13px] truncate">
            {item.label}
          </span>
          {item.badge && (
            <Badge
              variant="outline"
              className={cn(
                "text-[9px] px-1.5 py-0 h-[18px] font-mono font-semibold shrink-0 rounded-md",
                item.badgeColor || "border-border text-muted-foreground",
              )}
            >
              {item.badge}
            </Badge>
          )}
        </>
      )}
    </Link>
  );
}
