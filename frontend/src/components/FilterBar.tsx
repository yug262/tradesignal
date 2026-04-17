import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { NewsFilter } from "@/types/trading";
import { Filter, X } from "lucide-react";

// Extended filter model with additional UI-layer fields
export interface ExtendedNewsFilter extends NewsFilter {
  dateRange: "today" | "7days" | "all";
  relevance: "all" | "high" | "medium" | "low";
  pageSize: number;
}

interface FilterBarProps {
  filters: ExtendedNewsFilter;
  onChange: (filters: ExtendedNewsFilter) => void;
  totalShowing: number;
  totalAvailable: number;
}

const CATEGORIES = [
  { value: "all", label: "All Categories" },
  { value: "earnings", label: "Earnings" },
  { value: "merger", label: "Merger / M&A" },
  { value: "regulatory", label: "Regulatory" },
  { value: "macro", label: "Macro" },
  { value: "product", label: "Product" },
  { value: "analyst", label: "Analyst" },
  { value: "other", label: "Other" },
];

const IMPACT_LEVELS = [
  { value: "0", label: "All Impact" },
  { value: "8", label: "High (8+)" },
  { value: "5", label: "Medium (5+)" },
  { value: "0.1", label: "Low (<5)" },
];

const DATE_RANGES = [
  { value: "all", label: "All Time" },
  { value: "today", label: "Today" },
  { value: "7days", label: "Last 7 Days" },
];

const RELEVANCE_OPTS = [
  { value: "all", label: "All Relevance" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const PAGE_SIZES = [
  { value: "10", label: "10 / page" },
  { value: "25", label: "25 / page" },
  { value: "50", label: "50 / page" },
];

function hasActiveFilters(f: ExtendedNewsFilter): boolean {
  return !!(
    f.symbol ||
    (f.category && f.category !== "all") ||
    (f.minImpact && f.minImpact > 0) ||
    f.dateRange !== "all" ||
    f.relevance !== "all"
  );
}

export function FilterBar({
  filters,
  onChange,
  totalShowing,
  totalAvailable,
}: FilterBarProps) {
  const active = hasActiveFilters(filters);

  function set<K extends keyof ExtendedNewsFilter>(
    key: K,
    value: ExtendedNewsFilter[K],
  ) {
    onChange({ ...filters, [key]: value });
  }

  function clearAll() {
    onChange({
      symbol: null,
      category: null,
      minImpact: null,
      dateRange: "all",
      relevance: "all",
      pageSize: filters.pageSize,
    });
  }

  return (
    <div
      className="sticky top-0 z-10 bg-background border-b border-border pb-3 pt-3 space-y-2"
      data-ocid="filter_bar"
    >
      {/* Top row: symbol search + filters + results count */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Symbol input */}
        <div className="relative">
          <Input
            placeholder="Symbol — e.g. AAPL"
            value={filters.symbol ?? ""}
            onChange={(e) =>
              set("symbol", e.target.value.toUpperCase() || null)
            }
            className="h-7 w-36 font-mono text-xs bg-card border-border pr-6 pl-2"
            data-ocid="filter_bar.symbol_input"
          />
          {filters.symbol && (
            <button
              type="button"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => set("symbol", null)}
              aria-label="Clear symbol"
            >
              <X size={10} />
            </button>
          )}
        </div>

        {/* Category */}
        <Select
          value={filters.category ?? "all"}
          onValueChange={(v) => set("category", v === "all" ? null : v)}
        >
          <SelectTrigger
            className="h-7 w-38 font-mono text-xs bg-card border-border"
            data-ocid="filter_bar.category_select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border">
            {CATEGORIES.map((c) => (
              <SelectItem
                key={c.value}
                value={c.value}
                className="font-mono text-xs"
              >
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Impact */}
        <Select
          value={String(filters.minImpact ?? "0")}
          onValueChange={(v) => {
            const n = Number.parseFloat(v);
            set("minImpact", n > 0 ? n : null);
          }}
        >
          <SelectTrigger
            className="h-7 w-32 font-mono text-xs bg-card border-border"
            data-ocid="filter_bar.impact_select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border">
            {IMPACT_LEVELS.map((l) => (
              <SelectItem
                key={l.value}
                value={l.value}
                className="font-mono text-xs"
              >
                {l.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Date Range */}
        <Select
          value={filters.dateRange}
          onValueChange={(v) =>
            set("dateRange", v as ExtendedNewsFilter["dateRange"])
          }
        >
          <SelectTrigger
            className="h-7 w-32 font-mono text-xs bg-card border-border"
            data-ocid="filter_bar.date_range_select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border">
            {DATE_RANGES.map((r) => (
              <SelectItem
                key={r.value}
                value={r.value}
                className="font-mono text-xs"
              >
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Relevance */}
        <Select
          value={filters.relevance}
          onValueChange={(v) =>
            set("relevance", v as ExtendedNewsFilter["relevance"])
          }
        >
          <SelectTrigger
            className="h-7 w-32 font-mono text-xs bg-card border-border"
            data-ocid="filter_bar.relevance_select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border">
            {RELEVANCE_OPTS.map((r) => (
              <SelectItem
                key={r.value}
                value={r.value}
                className="font-mono text-xs"
              >
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Clear */}
        {active && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 font-mono text-[10px] text-muted-foreground hover:text-foreground"
            onClick={clearAll}
            type="button"
            data-ocid="filter_bar.clear_button"
          >
            <X size={10} className="mr-1" />
            Clear
          </Button>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Page size */}
        <Select
          value={String(filters.pageSize)}
          onValueChange={(v) => set("pageSize", Number.parseInt(v))}
        >
          <SelectTrigger
            className="h-7 w-28 font-mono text-xs bg-card border-border"
            data-ocid="filter_bar.page_size_select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border">
            {PAGE_SIZES.map((p) => (
              <SelectItem
                key={p.value}
                value={p.value}
                className="font-mono text-xs"
              >
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Results row */}
      <div className="flex items-center gap-2">
        <Filter size={9} className="text-muted-foreground opacity-60" />
        <span className="font-mono text-[10px] text-muted-foreground opacity-70">
          Showing{" "}
          <span
            className={cn(
              "font-semibold",
              active ? "text-primary" : "text-foreground",
            )}
          >
            {totalShowing}
          </span>
          {" of "}
          <span className="text-foreground">{totalAvailable}</span>
          {" articles"}
        </span>
        {active && (
          <Badge
            variant="outline"
            className="font-mono text-[9px] px-1.5 py-0 h-4 border-primary/30 text-primary bg-primary/5 ml-1"
          >
            FILTERED
          </Badge>
        )}
      </div>
    </div>
  );
}
