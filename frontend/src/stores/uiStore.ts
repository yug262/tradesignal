import { create } from "zustand";

interface UIState {
  sidebarCollapsed: boolean;
  activePageTitle: string;
  lastRefreshTime: Date | null;
  theme: "light" | "dark";
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setActivePageTitle: (title: string) => void;
  setLastRefreshTime: (time: Date) => void;
  setTheme: (theme: "light" | "dark") => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  activePageTitle: "Dashboard",
  lastRefreshTime: null,
  theme: "dark",
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setActivePageTitle: (activePageTitle) => set({ activePageTitle }),
  setLastRefreshTime: (lastRefreshTime) => set({ lastRefreshTime }),
  setTheme: (theme) => set({ theme }),
  toggleTheme: () =>
    set((state) => ({ theme: state.theme === "dark" ? "light" : "dark" })),
}));
