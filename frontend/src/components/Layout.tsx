import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useRouterState } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppHeader } from "./AppHeader";
import { AppSidebar } from "./AppSidebar";

const ROUTE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/opportunities": "Live Opportunities",
  "/agent-signals": "Agent 1 — News Discovery",
  "/market-open": "Agent 2 — Market Open Validation",
  "/technical-analysis": "Agent 2.5 — Technical Analysis",
  "/execution-planner": "Agent 3 — Execution Planner",
  "/news-feed": "News Feed",
  "/grouping": "Stock Grouping",
  "/paper-trading": "Paper Trading",
  "/mode-analysis": "Mode Analysis",
  "/trade-planner": "Trade Planner",
  "/journal": "Journal & History",
  "/market-regime": "Market Regime",
  "/settings": "Settings",
};

function getPageTitle(pathname: string): string {
  if (pathname.startsWith("/symbols/")) {
    const symbol = pathname.split("/symbols/")[1];
    return `Symbol: ${symbol?.toUpperCase() ?? "—"}`;
  }
  return ROUTE_TITLES[pathname] ?? "TradeSignal";
}

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const routerState = useRouterState();
  const theme = useUIStore((s) => s.theme);
  const setActivePageTitle = useUIStore((s) => s.setActivePageTitle);
  const currentPath = routerState.location.pathname;

  useEffect(() => {
    setActivePageTitle(getPageTitle(currentPath));
  }, [currentPath, setActivePageTitle]);

  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(theme);
  }, [theme]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <AppSidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <AppHeader />
        <main
          className="flex-1 overflow-y-auto bg-background"
          data-ocid="main_content"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
