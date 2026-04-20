import type { SystemConfig } from "@/types/trading";
import { create } from "zustand";

interface SettingsState {
  config: SystemConfig | null;
  isLoading: boolean;
  lastSaved: Date | null;
  setConfig: (config: SystemConfig) => void;
  setLoading: (loading: boolean) => void;
  setLastSaved: (date: Date) => void;
}

const DEFAULT_CONFIG: SystemConfig = {
  capital: 100000,
  risk_per_trade_pct: 1.0,
  max_open_positions: 5,
  max_daily_loss_pct: 3.0,
  min_rr: 2.0,
  news_endpoint_url: "https://api.example.com/news",
  polling_interval_mins: 5,
  processing_mode: "PRE-MARKET",
};

export const useSettingsStore = create<SettingsState>((set) => ({
  config: DEFAULT_CONFIG,
  isLoading: false,
  lastSaved: null,
  setConfig: (config) => set({ config }),
  setLoading: (isLoading) => set({ isLoading }),
  setLastSaved: (lastSaved) => set({ lastSaved }),
}));
