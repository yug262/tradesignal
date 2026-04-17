import { create } from "zustand";

interface UIState {
  sidebarCollapsed: boolean;
  activePageTitle: string;
  lastRefreshTime: Date | null;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setActivePageTitle: (title: string) => void;
  setLastRefreshTime: (time: Date) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  activePageTitle: "Dashboard",
  lastRefreshTime: null,
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setActivePageTitle: (activePageTitle) => set({ activePageTitle }),
  setLastRefreshTime: (lastRefreshTime) => set({ lastRefreshTime }),
}));
