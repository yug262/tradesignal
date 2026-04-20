import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

// Define the types based on the backend response
interface Agent1Summary {
  watch: number;
  ignore: number;
  stale: number;
  high: number;
  medium: number;
  low: number;
}

interface Agent1Reasoning {
  decision: string;
  trade_preference: string;
  direction_bias: string;
  gap_expectation: string;
  priority: string;
  event_summary: string;
  event_strength: string;
  final_summary: string;
  open_expectation: string;
  key_drivers: string[];
  risks: string[];
  open_confirmation_needed: string[];
  invalid_if: string[];
}

interface Agent1Signal {
  id: string;
  symbol: string;
  signal_type: string;
  trade_mode: string;
  confidence: number;
  reasoning: Agent1Reasoning;
  stock_snapshot: any;
}

interface Agent1Result {
  run_id: string;
  market_date: string;
  generated_at: number;
  total_analyzed: number;
  signals_summary: Agent1Summary;
  signals: Agent1Signal[];
  duration_ms: number;
}

type DecisionFilter = "ALL" | "WATCH" | "IGNORE" | "STALE";

export function Agent1ResultsPage() {
  const [result, setResult] = useState<Agent1Result | null>(null);
  const [filter, setFilter] = useState<DecisionFilter>("ALL");

  const mutation = useMutation<Agent1Result, Error>({
    mutationFn: () => api.post("/api/agent/run").then((res) => res.data),
    onSuccess: (data) => {
      // Sort signals: WATCH > others > IGNORE/STALE, then by confidence
      const sortedSignals = [...data.signals].sort((a, b) => {
        const getScore = (decision: string) => {
          const upperCaseDecision = decision.toUpperCase();
          if (upperCaseDecision.includes("WATCH")) return 0;
          if (upperCaseDecision.includes("STALE") || upperCaseDecision.includes("IGNORE")) return 2;
          return 1;
        };
        const scoreA = getScore(a.reasoning.decision);
        const scoreB = getScore(b.reasoning.decision);
        if (scoreA !== scoreB) {
          return scoreA - scoreB;
        }
        return b.confidence - a.confidence;
      });
      setResult({ ...data, signals: sortedSignals });
    },
  });

  const filteredSignals = useMemo(() => {
    if (!result) return [];
    if (filter === "ALL") return result.signals;
    return result.signals.filter(s => s.reasoning.decision.toUpperCase().includes(filter));
  }, [result, filter]);

  const getPriorityBadgeVariant = (priority: string) => {
    switch (priority?.toUpperCase()) {
      case "HIGH":
        return "destructive";
      case "MEDIUM":
        return "secondary";
      default:
        return "outline";
    }
  };

  const getSignalTypeBadgeVariant = (signalType: string) => {
    switch (signalType?.toUpperCase()) {
      case "BUY":
        return "success";
      case "SELL":
        return "destructive";
      case "HOLD":
        return "secondary";
      default:
        return "outline";
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Agent 1: Pre-Market Intelligence</h1>
          <p className="text-muted-foreground">
            Run the analysis to get a watchlist of stocks to watch based on recent news and market data.
          </p>
        </div>
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {mutation.isPending ? "Running Analysis..." : "Run Full Analysis"}
        </Button>
      </div>

      {mutation.isError && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p>An error occurred while running the agent analysis:</p>
            <pre className="mt-2 bg-muted p-2 rounded-md text-sm">
              {mutation.error.message}
            </pre>
          </CardContent>
        </Card>
      )}

      {result && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Analysis Summary</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <StatCard title="Run ID" value={result.run_id} />
              <StatCard title="Market Date" value={result.market_date} />
              <StatCard title="Total Analyzed" value={result.total_analyzed} />
              <StatCard title="Duration" value={`${result.duration_ms} ms`} />
              <StatCard title="Watch" value={result.signals_summary.watch} />
              <StatCard title="Ignore" value={result.signals_summary.ignore} />
              <StatCard title="Stale" value={result.signals_summary.stale} />
              <StatCard title="High Priority" value={result.signals_summary.high} />
              <StatCard title="Medium Priority" value={result.signals_summary.medium} />
              <StatCard title="Low Priority" value={result.signals_summary.low} />
            </CardContent>
          </Card>

          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">Watchlist Assessments ({filteredSignals.length})</h2>
              <ToggleGroup 
                type="single" 
                defaultValue="ALL"
                onValueChange={(value: DecisionFilter) => value && setFilter(value)}
                className="hidden md:flex"
              >
                <ToggleGroupItem value="ALL">All</ToggleGroupItem>
                <ToggleGroupItem value="WATCH">Watch</ToggleGroupItem>
                <ToggleGroupItem value="IGNORE">Ignore</ToggleGroupItem>
                <ToggleGroupItem value="STALE">Stale</ToggleGroupItem>
              </ToggleGroup>
            </div>
            <div className="space-y-4">
              {filteredSignals.map((signal) => (
                <Card key={signal.id}>
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <div>
                        <CardTitle className="text-lg">{signal.symbol}</CardTitle>
                        <p className="text-sm text-muted-foreground">{signal.reasoning.event_summary}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={getSignalTypeBadgeVariant(signal.signal_type)}>{signal.signal_type}</Badge>
                        <Badge variant={getPriorityBadgeVariant(signal.reasoning.priority)}>{signal.reasoning.priority} Priority</Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Accordion type="single" collapsible className="w-full">
                      <AccordionItem value="item-1">
                        <AccordionTrigger>View Detailed Analysis</AccordionTrigger>
                        <AccordionContent>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-4">
                              <InfoSection title="Decision" value={signal.reasoning.decision} />
                              <InfoSection title="Confidence" value={(signal.confidence * 100).toFixed(2) + "%"} />
                              <InfoSection title="Direction Bias" value={signal.reasoning.direction_bias} />
                              <InfoSection title="Gap Expectation" value={signal.reasoning.gap_expectation} />
                              <InfoSection title="Event Strength" value={signal.reasoning.event_strength} />
                              <InfoSection title="Trade Preference" value={signal.reasoning.trade_mode} />
                            </div>
                            <div className="space-y-4">
                               <InfoSection title="Final Summary" value={signal.reasoning.final_summary} />
                               <InfoSection title="Opening Expectation" value={signal.reasoning.open_expectation} />
                            </div>
                          </div>
                           <div className="mt-6 space-y-4">
                                <ListSection title="Key Drivers" items={signal.reasoning.key_drivers} />
                                <ListSection title="Risks" items={signal.reasoning.risks} />
                                <ListSection title="Confirmation Needed at Open" items={signal.reasoning.open_confirmation_needed} />
                                <ListSection title="Invalidation Conditions" items={signal.reasoning.invalid_if} />
                           </div>
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const StatCard = ({ title, value }: { title: string; value: string | number }) => (
  <div className="bg-muted p-4 rounded-lg">
    <p className="text-sm text-muted-foreground">{title}</p>
    <p className="text-xl font-bold">{value}</p>
  </div>
);

const InfoSection = ({ title, value }: { title: string; value: string }) => (
    <div>
        <h4 className="font-semibold text-sm mb-1">{title}</h4>
        <p className="text-sm text-muted-foreground">{value}</p>
    </div>
);

const ListSection = ({ title, items }: { title: string; items: string[] }) => (
    <div>
        <h4 className="font-semibold text-sm mb-2">{title}</h4>
        <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
            {items.map((item, index) => <li key={index}>{item}</li>)}
        </ul>
    </div>
);
