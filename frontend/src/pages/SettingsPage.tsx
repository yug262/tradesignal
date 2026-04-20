import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useProcessingState,
  useResetConfig,
  useResetProcessingState,
  useSystemConfig,
  useTriggerFetch,
  useUpdateConfig,
} from "@/hooks/useNewsItems";
import { cn } from "@/lib/utils";
import { useSettingsStore } from "@/stores/settingsStore";
import type { SystemConfig } from "@/types/trading";
import { msToDate } from "@/types/trading";
import {
  AlertTriangle,
  BarChart3,
  Database,
  DollarSign,
  Globe,
  RefreshCw,
  RotateCcw,
  Save,
  Settings,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

// ── Small field wrapper ───────────────────────────────────────────────────────
function Field({
  label,
  hint,
  id,
  children,
}: {
  label: string;
  hint?: string;
  id: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label
        htmlFor={id}
        className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider block"
      >
        {label}
      </Label>
      {children}
      {hint && (
        <p className="font-mono text-[9px] text-muted-foreground opacity-50 leading-relaxed">
          {hint}
        </p>
      )}
    </div>
  );
}

// ── Section divider ───────────────────────────────────────────────────────────
function SectionHeader({
  title,
  icon: Icon,
}: {
  title: string;
  icon: typeof Settings;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon size={11} className="text-primary shrink-0" />
      <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
        {title}
      </span>
      <Separator className="flex-1 opacity-20" />
    </div>
  );
}

// ── Slider row (range input) ──────────────────────────────────────────────────
function SliderField({
  label,
  hint,
  id,
  value,
  min,
  max,
  step,
  unit,
  onChange,
  ocid,
}: {
  label: string;
  hint?: string;
  id: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (v: number) => void;
  ocid: string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label
          htmlFor={id}
          className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider"
        >
          {label}
        </Label>
        <span className="font-mono text-xs text-primary font-bold tabular-nums">
          {value.toFixed(step < 1 ? 1 : 0)}
          {unit}
        </span>
      </div>
      <div className="relative h-1.5 bg-secondary rounded-full">
        <div
          className="absolute left-0 top-0 h-full bg-primary rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number.parseFloat(e.target.value))}
        className="w-full opacity-0 h-1 -mt-3 cursor-pointer"
        aria-label={label}
        data-ocid={ocid}
      />
      {hint && (
        <p className="font-mono text-[9px] text-muted-foreground opacity-50">
          {hint}
        </p>
      )}
    </div>
  );
}

// ── Read-only status row ──────────────────────────────────────────────────────
function StatusRow({
  label,
  value,
  mono = true,
}: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-b border-border/30 last:border-0">
      <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest shrink-0">
        {label}
      </span>
      <span
        className={cn(
          "text-[11px] text-foreground truncate max-w-[200px] text-right",
          mono && "font-mono",
        )}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}

// ── Settings page ─────────────────────────────────────────────────────────────
export function SettingsPage() {
  const { data: backendConfig, isLoading } = useSystemConfig();
  const { data: procState } = useProcessingState();
  const updateConfig = useUpdateConfig();
  const resetConfig = useResetConfig();
  const resetProcState = useResetProcessingState();
  const triggerFetch = useTriggerFetch();
  const { setConfig } = useSettingsStore();

  const [localConfig, setLocalConfig] = useState<SystemConfig | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetProcDialogOpen, setResetProcDialogOpen] = useState(false);

  useEffect(() => {
    if (backendConfig) {
      setLocalConfig({ ...backendConfig });
      setConfig(backendConfig);
    }
  }, [backendConfig, setConfig]);

  function update<K extends keyof SystemConfig>(
    key: K,
    value: SystemConfig[K],
  ) {
    setLocalConfig((prev) => {
      if (!prev) return prev;
      return { ...prev, [key]: value };
    });
    setIsDirty(true);
  }

  function handleSave() {
    if (!localConfig) return;
    updateConfig.mutate(localConfig, {
      onSuccess: (ok) => {
        if (ok) {
          setIsDirty(false);
          toast.success("Configuration saved successfully", { duration: 4000 });
        } else {
          toast.error("Save failed — check backend connection");
        }
      },
      onError: () => toast.error("Save failed — network error"),
    });
  }

  function handleReset() {
    setResetDialogOpen(false);
    resetConfig.mutate(undefined, {
      onSuccess: (cfg) => {
        if (cfg) {
          setLocalConfig({ ...cfg });
          setConfig(cfg);
          setIsDirty(false);
          toast.success("Configuration reset to defaults");
        }
      },
      onError: () => toast.error("Reset failed"),
    });
  }

  function handleResetProcState() {
    setResetProcDialogOpen(false);
    resetProcState.mutate(undefined, {
      onSuccess: () => {
        toast.info(
          "Not implemented in Phase 1 — processing state reset is available in Phase 2+",
        );
      },
      onError: () => toast.error("Reset failed"),
    });
  }

  const cfg = localConfig;

  return (
    <div className="p-5 max-w-3xl space-y-4" data-ocid="settings.page">
      {/* Header row */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Settings size={14} className="text-primary" />
          <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
            System Configuration
          </span>
          {isDirty && (
            <Badge
              variant="outline"
              className="font-mono text-[9px] px-2 py-0.5 border-primary/30 text-primary bg-primary/5"
              data-ocid="settings.unsaved_indicator"
            >
              <AlertTriangle size={8} className="mr-1" />
              UNSAVED CHANGES
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="font-mono text-[10px] h-7 px-3 border-border text-muted-foreground hover:text-foreground"
            onClick={() => setResetDialogOpen(true)}
            disabled={resetConfig.isPending}
            type="button"
            data-ocid="settings.reset_button"
          >
            <RotateCcw size={10} className="mr-1.5" />
            Reset Defaults
          </Button>
          <Button
            size="sm"
            className="font-mono text-[10px] h-7 px-4 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
            onClick={handleSave}
            disabled={!isDirty || updateConfig.isPending || !cfg}
            type="button"
            data-ocid="settings.save_button"
          >
            <Save size={10} className="mr-1.5" />
            {updateConfig.isPending ? "Saving..." : "SAVE CONFIGURATION"}
          </Button>
        </div>
      </div>

      {/* Success/error banners */}
      {updateConfig.isSuccess && !isDirty && (
        <div
          className="flex items-center gap-2 p-2.5 rounded bg-chart-1/10 border border-chart-1/20 font-mono text-[11px] text-chart-1"
          data-ocid="settings.success_state"
        >
          ✓ Configuration saved and applied
        </div>
      )}
      {updateConfig.isError && (
        <div
          className="flex items-center gap-2 p-2.5 rounded bg-destructive/10 border border-destructive/20 font-mono text-[11px] text-destructive"
          data-ocid="settings.error_state"
        >
          ✗ Failed to save — check backend connection
        </div>
      )}

      {isLoading || !cfg ? (
        <div
          className="bg-card border border-border rounded p-5 space-y-4"
          data-ocid="settings.loading_state"
        >
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-8 w-full" />
            </div>
          ))}
        </div>
      ) : (
        <Tabs defaultValue="capital" className="w-full">
          <TabsList
            className="bg-card border border-border rounded h-8 p-0.5 gap-0.5"
            data-ocid="settings.tabs"
          >
            <TabsTrigger
              value="capital"
              className="font-mono text-[10px] uppercase tracking-wider h-7 px-3 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
              data-ocid="settings.tab.capital"
            >
              <DollarSign size={10} className="mr-1" />
              Capital & Risk
            </TabsTrigger>
            <TabsTrigger
              value="endpoint"
              className="font-mono text-[10px] uppercase tracking-wider h-7 px-3 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
              data-ocid="settings.tab.endpoint"
            >
              <Globe size={10} className="mr-1" />
              News Endpoint
            </TabsTrigger>
            <TabsTrigger
              value="status"
              className="font-mono text-[10px] uppercase tracking-wider h-7 px-3 data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
              data-ocid="settings.tab.status"
            >
              <Database size={10} className="mr-1" />
              System Status
            </TabsTrigger>
          </TabsList>

          {/* ── TAB 1: CAPITAL & RISK ──────────────────────────────────── */}
          <TabsContent value="capital" className="mt-3">
            <div className="bg-card border border-border rounded p-5 space-y-5">
              <SectionHeader title="Capital Parameters" icon={DollarSign} />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <Field
                  label="Total Capital (USD)"
                  hint="Total account capital used for position sizing"
                  id="capital"
                >
                  <Input
                    id="capital"
                    type="number"
                    value={cfg.capital}
                    onChange={(e) =>
                      update("capital", Number.parseFloat(e.target.value) || 0)
                    }
                    className="h-8 font-mono text-xs bg-background border-border"
                    min={0}
                    data-ocid="settings.capital_input"
                  />
                </Field>

                <Field
                  label="Max Open Positions"
                  hint="Hard cap on concurrent open trades"
                  id="max_positions"
                >
                  <Input
                    id="max_positions"
                    type="number"
                    value={Number(cfg.max_open_positions)}
                    onChange={(e) =>
                      update(
                        "max_open_positions",
                        Number.parseInt(e.target.value) || 1,
                      )
                    }
                    className="h-8 font-mono text-xs bg-background border-border"
                    min={1}
                    max={20}
                    data-ocid="settings.max_positions_input"
                  />
                </Field>
              </div>

              <SectionHeader title="Risk Parameters" icon={ShieldAlert} />

              <div className="space-y-5">
                <SliderField
                  label="Risk Per Trade"
                  hint="Maximum capital risked per single trade"
                  id="risk_per_trade"
                  value={cfg.risk_per_trade_pct}
                  min={0.5}
                  max={5}
                  step={0.1}
                  unit="%"
                  onChange={(v) => update("risk_per_trade_pct", v)}
                  ocid="settings.risk_per_trade_slider"
                />
                <SliderField
                  label="Max Daily Loss"
                  hint="Circuit breaker — halt all new trades if reached"
                  id="max_daily_loss"
                  value={cfg.max_daily_loss_pct}
                  min={1}
                  max={10}
                  step={0.5}
                  unit="%"
                  onChange={(v) => update("max_daily_loss_pct", v)}
                  ocid="settings.max_daily_loss_slider"
                />
              </div>

              <Field
                label="Minimum Risk/Reward Ratio"
                hint="Trades with RR below this threshold are rejected by the risk engine"
                id="min_rr"
              >
                <div className="flex items-center gap-3">
                  <Input
                    id="min_rr"
                    type="number"
                    value={cfg.min_rr}
                    onChange={(e) =>
                      update("min_rr", Number.parseFloat(e.target.value) || 1)
                    }
                    className="h-8 font-mono text-xs bg-background border-border w-28"
                    min={1}
                    max={10}
                    step={0.1}
                    data-ocid="settings.min_rr_input"
                  />
                  <span className="font-mono text-[10px] text-muted-foreground opacity-60">
                    e.g. 1.5 = 1.5× reward for every 1× risk
                  </span>
                </div>
              </Field>
            </div>
          </TabsContent>

          {/* ── TAB 2: NEWS ENDPOINT ───────────────────────────────────── */}
          <TabsContent value="endpoint" className="mt-3">
            <div className="bg-card border border-border rounded p-5 space-y-5">
              <SectionHeader title="News Source Configuration" icon={Globe} />

              <Field
                label="Endpoint URL"
                hint="External news platform API endpoint — must return analyzed articles"
                id="endpoint_url"
              >
                <Input
                  id="endpoint_url"
                  type="url"
                  value={cfg.news_endpoint_url}
                  onChange={(e) => update("news_endpoint_url", e.target.value)}
                  className="h-8 font-mono text-xs bg-background border-border"
                  placeholder="https://api.example.com/news"
                  data-ocid="settings.endpoint_url_input"
                />
              </Field>


              <SectionHeader
                title="Processing Configuration"
                icon={BarChart3}
              />

              {/* Processing mode radio */}
              <div className="space-y-1.5">
                <Label className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider block">
                  Processing Mode
                </Label>
                <div
                  className="grid grid-cols-1 sm:grid-cols-3 gap-2"
                  data-ocid="settings.processing_mode_group"
                >
                  {["PRE-MARKET", "LIVE", "BATCH"].map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={cn(
                        "flex flex-col items-start p-3 rounded border font-mono text-xs transition-smooth",
                        cfg.processing_mode === mode
                          ? "bg-primary/10 border-primary/40 text-primary"
                          : "bg-background border-border text-muted-foreground hover:border-border/70 hover:text-foreground",
                      )}
                      onClick={() => update("processing_mode", mode)}
                      data-ocid={`settings.mode_option.${mode.toLowerCase().replace("-", "_")}`}
                    >
                      <span className="font-semibold text-[11px] uppercase">
                        {mode}
                      </span>
                      <span className="text-[9px] mt-0.5 opacity-70 leading-relaxed">
                        {mode === "PRE-MARKET"
                          ? "Batch before market open"
                          : mode === "LIVE"
                            ? "Continuous real-time polling"
                            : "Manual batch trigger only"}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <SliderField
                label="Polling Interval"
                hint="How often to fetch new articles in live mode"
                id="polling_interval"
                value={Number(cfg.polling_interval_mins)}
                min={1}
                max={60}
                step={1}
                unit=" min"
                onChange={(v) =>
                  update("polling_interval_mins", Math.round(v))
                }
                ocid="settings.polling_interval_slider"
              />

              {/* Manual fetch */}
              <div className="pt-1 border-t border-border/30">
                <Button
                  variant="outline"
                  size="sm"
                  className="font-mono text-[10px] h-8 px-4 border-primary/30 text-primary hover:bg-primary/10 hover:border-primary/50 uppercase tracking-wider"
                  onClick={() => {
                    triggerFetch.mutate(undefined, {
                      onSuccess: () =>
                        toast.success("Fetch triggered successfully"),
                      onError: () => toast.error("Fetch failed"),
                    });
                  }}
                  disabled={triggerFetch.isPending}
                  type="button"
                  data-ocid="settings.fetch_now_button"
                >
                  <RefreshCw
                    size={10}
                    className={cn(
                      "mr-1.5",
                      triggerFetch.isPending && "animate-spin",
                    )}
                  />
                  {triggerFetch.isPending ? "Fetching..." : "FETCH NEWS NOW"}
                </Button>
                {triggerFetch.isSuccess && (
                  <span className="ml-3 font-mono text-[10px] text-chart-1">
                    ✓ Fetch completed
                  </span>
                )}
              </div>
            </div>
          </TabsContent>

          {/* ── TAB 3: SYSTEM STATUS ───────────────────────────────────── */}
          <TabsContent value="status" className="mt-3">
            <div className="bg-card border border-border rounded p-5 space-y-5">
              <SectionHeader title="Processing State" icon={Database} />

              {procState ? (
                <div className="bg-background border border-border rounded p-3 space-y-0">
                  <StatusRow
                    label="Last Processed ID"
                    value={procState.last_processed_article_id ?? "— none —"}
                  />
                  <StatusRow
                    label="Last Poll"
                    value={
                       procState.last_poll_timestamp > 0
                        ? `${msToDate(procState.last_poll_timestamp)
                            .toISOString()
                            .replace("T", " ")
                            .slice(0, 19)} UTC`
                        : "Never"
                    }
                  />
                  <StatusRow
                    label="Total Processed"
                    value={procState.total_articles_processed.toLocaleString()}
                  />
                  <StatusRow
                    label="Articles In Queue"
                    value={procState.articles_in_queue.toLocaleString()}
                  />
                  <StatusRow
                    label="Current Mode"
                    value={procState.current_mode}
                  />
                  <StatusRow
                    label="Polling Active"
                    value={procState.is_polling_active ? "YES" : "NO"}
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <Skeleton key={i} className="h-8 w-full" />
                  ))}
                </div>
              )}

              {/* Reset state */}
              <div className="pt-2 border-t border-border/30 space-y-2">
                <div className="font-mono text-[10px] text-muted-foreground opacity-70 leading-relaxed">
                  Resetting processing state will clear the last processed
                  article ID and queue counter. This does not delete articles —
                  it resets the processing cursor.
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="font-mono text-[10px] h-7 border-destructive/30 text-destructive hover:bg-destructive/10"
                  onClick={() => setResetProcDialogOpen(true)}
                  type="button"
                  data-ocid="settings.reset_state_button"
                >
                  <RotateCcw size={10} className="mr-1.5" />
                  Reset Processing State
                </Button>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      )}

      {/* Reset confirmation dialog */}
      <Dialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <DialogContent
          className="bg-popover border-border max-w-sm"
          data-ocid="settings.reset_dialog"
        >
          <DialogHeader>
            <DialogTitle className="font-display text-sm font-semibold text-foreground flex items-center gap-2">
              <AlertTriangle size={14} className="text-primary" />
              Confirm Reset
            </DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground leading-relaxed">
            This will reset all configuration to factory defaults. Current
            settings will be overwritten. This action cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              size="sm"
              className="font-mono text-[10px] h-7 border-border"
              onClick={() => setResetDialogOpen(false)}
              type="button"
              data-ocid="settings.reset_dialog.cancel_button"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="font-mono text-[10px] h-7 bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={handleReset}
              disabled={resetConfig.isPending}
              type="button"
              data-ocid="settings.reset_dialog.confirm_button"
            >
              {resetConfig.isPending ? "Resetting..." : "RESET TO DEFAULTS"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset processing state dialog */}
      <Dialog open={resetProcDialogOpen} onOpenChange={setResetProcDialogOpen}>
        <DialogContent
          className="bg-popover border-border max-w-sm"
          data-ocid="settings.reset_proc_dialog"
        >
          <DialogHeader>
            <DialogTitle className="font-display text-sm font-semibold text-foreground flex items-center gap-2">
              <AlertTriangle size={14} className="text-destructive" />
              Reset Processing State
            </DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground leading-relaxed">
            This will clear the last processed article ID and queue counter,
            resetting the processing cursor. Articles are not deleted. This
            action cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              size="sm"
              className="font-mono text-[10px] h-7 border-border"
              onClick={() => setResetProcDialogOpen(false)}
              type="button"
              data-ocid="settings.reset_proc_dialog.cancel_button"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="font-mono text-[10px] h-7 bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleResetProcState}
              disabled={resetProcState.isPending}
              type="button"
              data-ocid="settings.reset_proc_dialog.confirm_button"
            >
              {resetProcState.isPending ? "Resetting..." : "RESET STATE"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
