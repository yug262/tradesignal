import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/uiStore";
import { useRouterState } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppHeader } from "./AppHeader";
import { AppSidebar } from "./AppSidebar";

const ROUTE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/opportunities": "Live Trade Opportunities",
  "/news-feed": "News-to-Trade Feed",
  "/mode-analysis": "Mode Analysis",
  "/trade-planner": "Trade Planner",
  "/journal": "Journal / History",
  "/market-regime": "Market Regime",
  "/settings": "Settings & Risk Config",
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

        {/* Branding footer */}
        <footer className="shrink-0 flex items-center justify-end px-4 py-1.5 bg-card border-t border-border">
          <span className="font-mono text-[10px] text-muted-foreground opacity-40">
            © {new Date().getFullYear()}. Built with love using{" "}
            <a
              href={`https://caffeine.ai?utm_source=caffeine-footer&utm_medium=referral&utm_content=${encodeURIComponent(
                typeof window !== "undefined" ? window.location.hostname : "",
              )}`}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-muted-foreground transition-colors"
            >
              caffeine.ai
            </a>
          </span>
        </footer>
      </div>
    </div>
  );
}
