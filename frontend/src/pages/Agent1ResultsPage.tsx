import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { api } from "@/backend";
import { useMutation } from "@tanstack/react-query";
import { Loader2, AlertCircle, CheckCircle2, Info, TrendingUp, RefreshCw } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

// ── Discovery Layer Types (Agent 1 output schema) ────────────────────────────
// This layer answers: "What actually happened, and does it meaningfully matter?"
// It does NOT produce direction bias, watchlist decisions, or trade preferences.

interface DiscoveryOutput {
  // Core event understanding
  event_summary: string;           // 1-2 sentence plain-English summary
  detailed_explanation: string;    // 4-6 sentence context
  event_type: "corporate_event" | "macro" | "sector" | "regulatory" | "other";
  event_strength: "STRONG" | "MODERATE" | "WEAK";
  freshness: "FRESH" | "SLIGHTLY_OLD" | "OLD" | "REPEATED";
  directness: "DIRECT" | "INDIRECT" | "NONE";
  is_material: boolean;
  impact_analysis: string;         // Business impact narrative
  key_positive_factors: string[];
  key_risks: string[];
  confidence: number;              // 0-100
  final_verdict: "IMPORTANT_EVENT" | "MODERATE_EVENT" | "MINOR_EVENT" | "NOISE";
  reasoning_summary: string;
  _source: string;
  _model: string;
}

interface DiscoverySummary {
  watch: number;      // IMPORTANT_EVENT count (sent to Agent 2)
  ignore: number;     // MINOR_EVENT / NOISE count
  stale: number;      // NOISE with old/repeated freshness
  strong: number;
  moderate: number;
  weak: number;
}

interface DiscoverySignal {
  id: string;
  symbol: string;
  signal_type: string;   // WATCH | NO_TRADE (derived from final_verdict)
  trade_mode: string;    // Always "NONE" at Discovery stage
  confidence: number;
  reasoning: DiscoveryOutput;
  stock_snapshot: Record<string, unknown>;
}

interface DiscoveryResult {
  run_id: string;
  market_date: string;
  generated_at: number;
  total_analyzed: number;
  signals_summary: DiscoverySummary;
  signals: DiscoverySignal[];
  duration_ms: number;
}

type VerdictFilter = "ALL" | "IMPORTANT_EVENT" | "MODERATE_EVENT" | "MINOR_EVENT" | "NOISE";

// ── Verdict styling helpers ───────────────────────────────────────────────────

function getVerdictStyle(verdict: string): string {
  switch (verdict?.toUpperCase()) {
    case "IMPORTANT_EVENT":
      return "bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400";
    case "MODERATE_EVENT":
      return "bg-amber-500/10 text-amber-600 border-amber-500/30 dark:text-amber-400";
    case "MINOR_EVENT":
      return "bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-400";
    case "NOISE":
      return "bg-muted text-muted-foreground border-border";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function getStrengthStyle(strength: string): string {
  switch (strength?.toUpperCase()) {
    case "STRONG":
      return "bg-red-500/10 text-red-600 border-red-500/30 dark:text-red-400";
    case "MODERATE":
      return "bg-amber-500/10 text-amber-600 border-amber-500/30 dark:text-amber-400";
    case "WEAK":
      return "bg-muted text-muted-foreground border-border";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function getFreshnessStyle(freshness: string): string {
  switch (freshness?.toUpperCase()) {
    case "FRESH":
      return "text-emerald-600 dark:text-emerald-400";
    case "SLIGHTLY_OLD":
      return "text-amber-600 dark:text-amber-400";
    case "OLD":
    case "REPEATED":
      return "text-muted-foreground";
    default:
      return "text-muted-foreground";
  }
}

function getDirectnessBadge(directness: string): string {
  switch (directness?.toUpperCase()) {
    case "DIRECT":
      return "bg-primary/10 text-primary border-primary/30";
    case "INDIRECT":
      return "bg-secondary text-muted-foreground border-border";
    case "NONE":
      return "bg-muted text-muted-foreground/60 border-border";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function verdictLabel(verdict: string): string {
  const map: Record<string, string> = {
    IMPORTANT_EVENT: "Important",
    MODERATE_EVENT: "Moderate",
    MINOR_EVENT: "Minor",
    NOISE: "Noise",
  };
  return map[verdict?.toUpperCase?.()] ?? verdict ?? "—";
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function Agent1ResultsPage() {
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [filter, setFilter] = useState<VerdictFilter>("ALL");

  const mutation = useMutation<DiscoveryResult, Error>({
    mutationFn: () => api.triggerAgentRun(),
    onSuccess: (data) => {
      // Sort signals: IMPORTANT_EVENT first, then MODERATE, then others, then by confidence
      const verdictOrder: Record<string, number> = {
        IMPORTANT_EVENT: 0,
        MODERATE_EVENT: 1,
        MINOR_EVENT: 2,
        NOISE: 3,
      };
      const sortedSignals = [...data.signals].sort((a, b) => {
        const va = verdictOrder[a.reasoning?.final_verdict?.toUpperCase?.()] ?? 4;
        const vb = verdictOrder[b.reasoning?.final_verdict?.toUpperCase?.()] ?? 4;
        if (va !== vb) return va - vb;
        return b.confidence - a.confidence;
      });
      setResult({ ...data, signals: sortedSignals });
    },
  });

  const filteredSignals = useMemo(() => {
    if (!result) return [];
    if (filter === "ALL") return result.signals;
    return result.signals.filter(
      (s) => s.reasoning?.final_verdict?.toUpperCase?.() === filter
    );
  }, [result, filter]);

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Discovery Agent · Agent 1</h1>
          <p className="text-muted-foreground text-sm mt-1">
            News understanding layer — explains what actually happened and whether it matters.
            Does <em>not</em> predict direction or give trading advice.
          </p>
        </div>
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending} id="run-discovery-btn">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {mutation.isPending ? "Running Discovery..." : "Run Discovery Analysis"}
        </Button>
      </div>

      {/* Error State */}
      {mutation.isError && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center gap-2">
              <AlertCircle className="h-4 w-4" /> Error
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="mt-2 bg-muted p-2 rounded-md text-sm whitespace-pre-wrap">
              {mutation.error.message}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Run Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                Discovery Run Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <StatCard title="Run ID" value={result.run_id} />
              <StatCard title="Market Date" value={result.market_date} />
              <StatCard title="Symbols Analyzed" value={result.total_analyzed} />
              <StatCard title="Duration" value={`${result.duration_ms} ms`} />
              <StatCard
                title="Important Events"
                value={result.signals_summary.watch}
                highlight
              />
              <StatCard title="Minor / Noise" value={result.signals_summary.ignore} />
              <StatCard title="Stale / Repeated" value={result.signals_summary.stale} />
              <StatCard title="Strong Events" value={result.signals_summary.strong} />
            </CardContent>
          </Card>

          {/* Signals List */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">
                Event Assessments ({filteredSignals.length})
              </h2>
              <ToggleGroup
                type="single"
                defaultValue="ALL"
                onValueChange={(value: VerdictFilter) => value && setFilter(value)}
                className="hidden md:flex"
              >
                <ToggleGroupItem value="ALL">All</ToggleGroupItem>
                <ToggleGroupItem value="IMPORTANT_EVENT">Important</ToggleGroupItem>
                <ToggleGroupItem value="MODERATE_EVENT">Moderate</ToggleGroupItem>
                <ToggleGroupItem value="MINOR_EVENT">Minor</ToggleGroupItem>
                <ToggleGroupItem value="NOISE">Noise</ToggleGroupItem>
              </ToggleGroup>
            </div>

            <div className="space-y-4">
              {filteredSignals.map((signal) => {
                const r = signal.reasoning ?? {};
                return (
                  <Card key={signal.id} className="overflow-hidden">
                    <CardHeader className="pb-3">
                      <div className="flex justify-between items-start gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <CardTitle className="text-lg">{signal.symbol}</CardTitle>
                            <Badge
                              variant="outline"
                              className={`text-[10px] font-bold tracking-wider ${getVerdictStyle(r.final_verdict)}`}
                            >
                              {verdictLabel(r.final_verdict)}
                            </Badge>
                            <Badge
                              variant="outline"
                              className={`text-[10px] font-bold tracking-wider ${getStrengthStyle(r.event_strength)}`}
                            >
                              {r.event_strength ?? "—"}
                            </Badge>
                            {r.is_material && (
                              <Badge
                                variant="outline"
                                className="text-[10px] bg-primary/10 text-primary border-primary/30"
                              >
                                MATERIAL
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground leading-relaxed">
                            {r.event_summary}
                          </p>
                        </div>
                        <div className="text-right shrink-0">
                          <p className="text-2xl font-bold tabular-nums">{signal.confidence}%</p>
                          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">confidence</p>
                        </div>
                      </div>

                      {/* Quick-scan metadata row */}
                      <div className="flex gap-2 flex-wrap mt-2">
                        <Badge variant="outline" className="text-[10px]">
                          {r.event_type?.replace("_", " ") ?? "—"}
                        </Badge>
                        <Badge
                          variant="outline"
                          className={`text-[10px] ${getDirectnessBadge(r.directness)}`}
                        >
                          {r.directness ?? "—"}
                        </Badge>
                        <span className={`text-[11px] font-mono ${getFreshnessStyle(r.freshness)}`}>
                          ↻ {r.freshness ?? "—"}
                        </span>
                      </div>
                    </CardHeader>

                    <CardContent className="pt-0">
                      <Accordion type="single" collapsible className="w-full">
                        <AccordionItem value="detail">
                          <AccordionTrigger className="text-sm">
                            View Full Discovery Analysis
                          </AccordionTrigger>
                          <AccordionContent>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                              {/* Left column */}
                              <div className="space-y-5">
                                <InfoSection
                                  title="Detailed Explanation"
                                  value={r.detailed_explanation}
                                />
                                <InfoSection
                                  title="Business Impact Analysis"
                                  value={r.impact_analysis}
                                />
                                <InfoSection
                                  title="Reasoning Summary"
                                  value={r.reasoning_summary}
                                />
                              </div>

                              {/* Right column */}
                              <div className="space-y-5">
                                <ListSection
                                  title="Key Positive Factors"
                                  items={r.key_positive_factors ?? []}
                                  emptyText="None identified"
                                  icon="✓"
                                  iconClass="text-emerald-500"
                                />
                                <ListSection
                                  title="Key Risks"
                                  items={r.key_risks ?? []}
                                  emptyText="None identified"
                                  icon="⚠"
                                  iconClass="text-amber-500"
                                />
                              </div>
                            </div>

                            {/* Footer meta */}
                            <div className="mt-5 pt-4 border-t border-border flex gap-4 flex-wrap text-[10px] text-muted-foreground font-mono">
                              <span>source: {r._source ?? "—"}</span>
                              <span>model: {r._model ?? "—"}</span>
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      </Accordion>
                    </CardContent>
                  </Card>
                );
              })}

              {filteredSignals.length === 0 && (
                <div className="text-center py-16 text-muted-foreground">
                  <Info className="mx-auto h-8 w-8 opacity-30 mb-3" />
                  <p className="text-sm">No events match the selected filter.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Empty / initial state */}
      {!result && !mutation.isPending && (
        <div className="text-center py-20 text-muted-foreground space-y-4">
          <TrendingUp className="mx-auto h-10 w-10 opacity-20" />
          <p className="text-sm">
            No discovery run yet. Click <strong>Run Discovery Analysis</strong> to begin.
          </p>
          <p className="text-xs opacity-60">
            Agent 1 reads recent news and explains what happened — without any directional prediction.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

const StatCard = ({
  title,
  value,
  highlight = false,
}: {
  title: string;
  value: string | number;
  highlight?: boolean;
}) => (
  <div className={`p-4 rounded-lg border ${highlight ? "bg-emerald-500/5 border-emerald-500/20" : "bg-muted border-transparent"}`}>
    <p className="text-sm text-muted-foreground">{title}</p>
    <p className={`text-xl font-bold ${highlight ? "text-emerald-600 dark:text-emerald-400" : ""}`}>
      {value}
    </p>
  </div>
);

const InfoSection = ({ title, value }: { title: string; value?: string }) => (
  <div>
    <h4 className="font-semibold text-xs text-muted-foreground uppercase tracking-wider mb-1.5">
      {title}
    </h4>
    <p className="text-sm leading-relaxed">{value ?? "—"}</p>
  </div>
);

const ListSection = ({
  title,
  items,
  emptyText = "None",
  icon,
  iconClass,
}: {
  title: string;
  items: string[];
  emptyText?: string;
  icon?: string;
  iconClass?: string;
}) => (
  <div>
    <h4 className="font-semibold text-xs text-muted-foreground uppercase tracking-wider mb-2">
      {title}
    </h4>
    {items.length === 0 ? (
      <p className="text-xs text-muted-foreground italic">{emptyText}</p>
    ) : (
      <ul className="space-y-1.5">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm text-muted-foreground">
            {icon && (
              <span className={`shrink-0 mt-0.5 ${iconClass}`}>{icon}</span>
            )}
            <span>{item}</span>
          </li>
        ))}
      </ul>
    )}
  </div>
);
