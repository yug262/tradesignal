import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn, timeAgo } from "@/lib/utils";
import { bigIntToDate, getImpactLevel } from "@/types/trading";
import type { NewsArticleRef } from "@/types/trading";
import { Check, ChevronDown, Copy } from "lucide-react";
import { useState } from "react";

// ── Impact colours ────────────────────────────────────────────────────────────
const IMPACT_SCORE_STYLES: Record<string, string> = {
  high: "text-destructive border-destructive/30 bg-destructive/10",
  medium: "text-primary border-primary/30 bg-primary/10",
  low: "text-muted-foreground border-border bg-secondary",
};

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, string> = {
  analyzed: "text-chart-1 border-chart-1/30 bg-chart-1/10",
  candidate: "text-primary border-primary/30 bg-primary/10",
  no_trade: "text-muted-foreground border-border bg-secondary",
  new: "text-chart-4 border-chart-4/30 bg-chart-4/10",
  planned: "text-chart-1 border-chart-1/30 bg-chart-1/10",
  processed: "text-chart-1 border-chart-1/30 bg-chart-1/10",
  pending: "text-primary border-primary/30 bg-primary/10",
  skipped: "text-muted-foreground border-border bg-secondary",
};

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    analyzed: "PROCESSED",
    no_trade: "NO-TRADE",
    candidate: "CANDIDATE",
    new: "PENDING",
    planned: "PLANNED",
    processed: "PROCESSED",
    pending: "PENDING",
    skipped: "SKIPPED",
  };
  return map[status] ?? status.toUpperCase();
}

// ── Analysis data renderer ────────────────────────────────────────────────────
function tryParseRawData(raw: string): Record<string, string> | null {
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null) {
      return parsed as Record<string, string>;
    }
  } catch {
    // not JSON
  }
  return null;
}

// ── Compact card (dashboard) ──────────────────────────────────────────────────
function CompactCard({
  article,
  idx,
}: {
  article: NewsArticleRef;
  idx: number;
}) {
  const impact = getImpactLevel(article.impact_score);
  const pubDate = bigIntToDate(article.published_at);

  return (
    <div
      className="bg-card border border-border rounded p-3 flex items-start gap-3 hover:border-border/70 transition-smooth"
      data-ocid={`news_article_card.item.${idx + 1}`}
    >
      {/* Impact score pill */}
      <Badge
        variant="outline"
        className={cn(
          "font-mono text-[10px] px-1.5 py-0 h-5 shrink-0 mt-0.5",
          IMPACT_SCORE_STYLES[impact],
        )}
      >
        {article.impact_score.toFixed(1)}
      </Badge>

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1">
        <p className="text-xs text-foreground font-medium leading-snug line-clamp-1">
          {article.title}
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-[10px] text-muted-foreground">
            {article.source}
          </span>
          <span className="text-border opacity-60">·</span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {timeAgo(pubDate)}
          </span>
          {article.news_category && (
            <Badge
              variant="outline"
              className="font-mono text-[9px] px-1.5 py-0 h-4 border-border text-muted-foreground"
            >
              {article.news_category}
            </Badge>
          )}
          {article.affected_symbols.length > 0 && (
            <div className="flex gap-1 ml-auto">
              {article.affected_symbols.slice(0, 3).map((sym) => (
                <span
                  key={sym}
                  className="font-mono text-[10px] text-primary font-semibold"
                >
                  ${sym}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Status */}
      <Badge
        variant="outline"
        className={cn(
          "font-mono text-[9px] px-1.5 py-0 h-4 uppercase shrink-0",
          STATUS_STYLES[article.processing_status] ??
            "text-muted-foreground border-border",
        )}
      >
        {statusLabel(article.processing_status)}
      </Badge>
    </div>
  );
}

// ── Full card with expand sheet ───────────────────────────────────────────────
function FullCard({
  article,
  idx,
}: {
  article: NewsArticleRef;
  idx: number;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const impact = getImpactLevel(article.impact_score);
  const pubDate = bigIntToDate(article.published_at);
  const analyzedDate = bigIntToDate(article.analyzed_at);
  const rawParsed = tryParseRawData(article.raw_analysis_data);

  function copyId() {
    navigator.clipboard.writeText(article.id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <>
      <div
        className="bg-card border border-border rounded p-4 space-y-3 hover:border-border/70 transition-smooth group"
        data-ocid={`news_article_card.item.${idx + 1}`}
      >
        {/* Top row */}
        <div className="flex items-start gap-2 flex-wrap">
          {/* Impact score */}
          <Badge
            variant="outline"
            className={cn(
              "font-mono text-[11px] px-2 py-0.5 font-bold",
              IMPACT_SCORE_STYLES[impact],
            )}
          >
            {article.impact_score.toFixed(1)} {impact.toUpperCase()}
          </Badge>

          {/* Category */}
          {article.news_category && (
            <Badge
              variant="outline"
              className="font-mono text-[9px] px-1.5 py-0.5 border-border text-muted-foreground uppercase"
            >
              {article.news_category}
            </Badge>
          )}

          {/* Relevance */}
          {article.news_relevance && (
            <Badge
              variant="outline"
              className="font-mono text-[9px] px-1.5 py-0.5 border-border text-muted-foreground uppercase"
            >
              {article.news_relevance} REL
            </Badge>
          )}

          <div className="ml-auto flex items-center gap-2">
            {/* Processing status */}
            <Badge
              variant="outline"
              className={cn(
                "font-mono text-[9px] px-1.5 py-0 h-5 uppercase",
                STATUS_STYLES[article.processing_status] ??
                  "text-muted-foreground border-border",
              )}
              data-ocid={`news_article_card.status.${idx + 1}`}
            >
              {article.processing_status === "analyzed" ||
              article.processing_status === "processed" ? (
                <span className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-chart-1" />
              ) : article.processing_status === "new" ||
                article.processing_status === "pending" ? (
                <span className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              ) : (
                <span className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-muted-foreground opacity-40" />
              )}
              {statusLabel(article.processing_status)}
            </Badge>

            {/* Time ago */}
            <span className="font-mono text-[10px] text-muted-foreground shrink-0">
              {timeAgo(pubDate)}
            </span>
          </div>
        </div>

        {/* Headline */}
        <p className="text-sm font-semibold text-foreground leading-snug line-clamp-2">
          {article.title}
        </p>

        {/* Source */}
        <p className="font-mono text-[10px] text-muted-foreground opacity-70">
          {article.source}
        </p>

        {/* Affected symbols */}
        {article.affected_symbols.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {article.affected_symbols.map((sym) => (
              <span
                key={sym}
                className="font-mono text-[10px] font-bold text-primary border border-primary/30 bg-primary/5 rounded px-1.5 py-0.5"
              >
                ${sym}
              </span>
            ))}
          </div>
        )}

        {/* Executive summary */}
        {article.executive_summary && (
          <p className="font-mono text-[10px] text-muted-foreground leading-relaxed line-clamp-2 opacity-80">
            {article.executive_summary}
          </p>
        )}

        {/* Bottom row */}
        <div className="flex items-center gap-4 flex-wrap pt-1 border-t border-border/30">
          <div className="flex items-center gap-1 font-mono text-[9px] text-muted-foreground">
            <span className="opacity-50">PUB</span>
            <span className="text-foreground">
              {pubDate.toLocaleTimeString("en-US", {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
              })}{" "}
              {pubDate.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </span>
          </div>
          <div className="flex items-center gap-1 font-mono text-[9px] text-muted-foreground">
            <span className="opacity-50">ANA</span>
            <span className="text-foreground">
              {analyzedDate.toLocaleTimeString("en-US", {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>

          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-6 px-2 font-mono text-[9px] text-muted-foreground hover:text-foreground uppercase tracking-wider gap-1"
            onClick={() => setSheetOpen(true)}
            type="button"
            data-ocid={`news_article_card.expand_button.${idx + 1}`}
          >
            <ChevronDown size={9} />
            Expand
          </Button>
        </div>
      </div>

      {/* Expanded Sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent
          side="right"
          className="w-[520px] max-w-full bg-popover border-border overflow-y-auto"
          data-ocid={`news_article_card.sheet.${idx + 1}`}
        >
          <SheetHeader className="space-y-1 pb-4 border-b border-border">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge
                variant="outline"
                className={cn(
                  "font-mono text-[10px]",
                  IMPACT_SCORE_STYLES[impact],
                )}
              >
                Impact {article.impact_score.toFixed(1)}
              </Badge>
              {article.news_category && (
                <Badge
                  variant="outline"
                  className="font-mono text-[9px] border-border text-muted-foreground uppercase"
                >
                  {article.news_category}
                </Badge>
              )}
              <Badge
                variant="outline"
                className={cn(
                  "font-mono text-[9px] uppercase",
                  STATUS_STYLES[article.processing_status] ??
                    "text-muted-foreground border-border",
                )}
              >
                {statusLabel(article.processing_status)}
              </Badge>
            </div>
            <SheetTitle className="text-sm font-semibold text-foreground leading-snug text-left">
              {article.title}
            </SheetTitle>
            <p className="font-mono text-[10px] text-muted-foreground">
              {article.source}
            </p>
          </SheetHeader>

          <div className="py-4 space-y-4">
            {/* Description */}
            {article.description && (
              <div className="space-y-1.5">
                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                  Description
                </span>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {article.description}
                </p>
              </div>
            )}

            {/* Impact summary */}
            {article.impact_summary && (
              <div className="space-y-1.5">
                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                  Impact Summary
                </span>
                <p className="font-mono text-xs text-foreground leading-relaxed bg-background border border-border rounded p-2.5">
                  {article.impact_summary}
                </p>
              </div>
            )}

            {/* Affected symbols */}
            {article.affected_symbols.length > 0 && (
              <div className="space-y-1.5">
                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                  Affected Symbols
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {article.affected_symbols.map((sym) => (
                    <span
                      key={sym}
                      className="font-mono text-xs font-bold text-primary border border-primary/30 bg-primary/5 rounded px-2 py-1"
                    >
                      ${sym}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Analysis data */}
            {article.raw_analysis_data && (
              <div className="space-y-1.5">
                <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                  Analysis Data
                </span>
                {rawParsed ? (
                  <div className="bg-background border border-border rounded p-2.5 space-y-1">
                    {Object.entries(rawParsed).map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-start justify-between gap-3"
                      >
                        <span className="font-mono text-[9px] text-muted-foreground uppercase shrink-0">
                          {k}
                        </span>
                        <span className="font-mono text-[10px] text-foreground text-right">
                          {String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <pre className="font-mono text-[10px] text-muted-foreground bg-background border border-border rounded p-2.5 overflow-x-auto whitespace-pre-wrap break-all">
                    {article.raw_analysis_data}
                  </pre>
                )}
              </div>
            )}

            {/* Timestamps */}
            <div className="space-y-1.5">
              <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                Timestamps
              </span>
              <div className="bg-background border border-border rounded p-2.5 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[9px] text-muted-foreground">
                    Published
                  </span>
                  <span className="font-mono text-[10px] text-foreground">
                    {pubDate.toISOString().replace("T", " ").slice(0, 19)} UTC
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[9px] text-muted-foreground">
                    Analyzed
                  </span>
                  <span className="font-mono text-[10px] text-foreground">
                    {analyzedDate.toISOString().replace("T", " ").slice(0, 19)}{" "}
                    UTC
                  </span>
                </div>
              </div>
            </div>

            {/* Article ID */}
            <div className="space-y-1.5">
              <span className="font-mono text-[9px] text-muted-foreground uppercase tracking-widest">
                Article ID
              </span>
              <div className="flex items-center gap-2 bg-background border border-border rounded px-2.5 py-2">
                <span className="font-mono text-[10px] text-muted-foreground truncate flex-1">
                  {article.id}
                </span>
                <button
                  type="button"
                  onClick={copyId}
                  className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="Copy article ID"
                  data-ocid={`news_article_card.copy_id.${idx + 1}`}
                >
                  {copied ? (
                    <Check size={12} className="text-chart-1" />
                  ) : (
                    <Copy size={12} />
                  )}
                </button>
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

// ── Public component ──────────────────────────────────────────────────────────
interface NewsArticleCardProps {
  article: NewsArticleRef;
  idx?: number;
  compact?: boolean;
  onClick?: () => void;
}

export function NewsArticleCard({
  article,
  idx = 0,
  compact = false,
}: NewsArticleCardProps) {
  if (compact) {
    return <CompactCard article={article} idx={idx} />;
  }
  return <FullCard article={article} idx={idx} />;
}
