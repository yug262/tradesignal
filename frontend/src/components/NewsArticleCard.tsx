import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn, timeAgo } from "@/lib/utils";
import { msToDate, getImpactLevel } from "@/types/trading";
import type { NewsArticleRef } from "@/types/trading";
import { Check, ChevronRight, Copy, Tag, Calendar, Activity, Newspaper, Quote } from "lucide-react";
import { useState } from "react";

// ── Impact colours ────────────────────────────────────────────────────────────
const IMPACT_SCORE_STYLES: Record<string, string> = {
  high: "text-red-500 border-red-500/30 bg-red-500/10 dark:text-red-400",
  medium: "text-amber-600 border-amber-500/30 bg-amber-500/10 dark:text-amber-400",
  low: "text-muted-foreground border-border bg-muted/50",
};

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, string> = {
  analyzed: "text-emerald-600 border-emerald-500/30 bg-emerald-500/10 dark:text-emerald-400",
  candidate: "text-blue-600 border-blue-500/30 bg-blue-500/10 dark:text-blue-400",
  no_trade: "text-muted-foreground border-border bg-muted",
  new: "text-purple-600 border-purple-500/30 bg-purple-500/10 dark:text-purple-400",
  planned: "text-emerald-600 border-emerald-500/30 bg-emerald-500/10 dark:text-emerald-400",
  processed: "text-emerald-600 border-emerald-500/30 bg-emerald-500/10 dark:text-emerald-400",
  pending: "text-blue-600 border-blue-500/30 bg-blue-500/10 dark:text-blue-400",
  skipped: "text-muted-foreground border-border bg-muted",
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

// ── Shared Detail Sheet ───────────────────────────────────────────────────────
interface ArticleDetailSheetProps {
  article: NewsArticleRef;
  idx: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function ArticleDetailSheet({ article, idx, open, onOpenChange }: ArticleDetailSheetProps) {
  const [copied, setCopied] = useState(false);
  const impact = getImpactLevel(article.impact_score);
  const pubDate = msToDate(article.published_at);
  const analyzedDate = msToDate(article.analyzed_at);

  function copyId() {
    navigator.clipboard.writeText(article.id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-[520px] max-w-full bg-background border-l border-border overflow-y-auto p-0 scrollbar-hide"
      >
        {/* Header Hero Section */}
        <div className="relative p-8 pb-6 border-b border-border bg-muted/20">
          <div className="flex items-center gap-3 mb-6">
            <Badge
              variant="outline"
              className={cn("px-2.5 py-0.5 text-[10px] font-bold tracking-wider rounded-md border-0", IMPACT_SCORE_STYLES[impact])}
            >
              IMPACT {article.impact_score.toFixed(1)}
            </Badge>
            <Badge
              variant="outline"
              className="px-2.5 py-0.5 text-[10px] font-medium tracking-wider bg-secondary border-border text-muted-foreground rounded-md"
            >
              {article.news_category?.toUpperCase() || "GENERAL"}
            </Badge>
            <Badge
              variant="outline"
              className={cn(
                "px-2.5 py-0.5 text-[10px] font-bold tracking-wider rounded-md border-0 ml-auto",
                STATUS_STYLES[article.processing_status]
              )}
            >
              {statusLabel(article.processing_status)}
            </Badge>
          </div>

          <h2 className="text-xl font-bold text-foreground leading-tight mb-4 tracking-tight">
            {article.title}
          </h2>

          <div className="flex items-center gap-4 text-muted-foreground font-mono text-[10px]">
            <div className="flex items-center gap-1.5">
              <Newspaper size={12} className="opacity-70" />
              <span>{article.source.toUpperCase()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Calendar size={12} className="opacity-70" />
              <span>{timeAgo(pubDate).toUpperCase()}</span>
            </div>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-8 space-y-10">
          {/* Executive Summary Section */}
          {article.executive_summary && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Quote size={14} className="text-primary opacity-60" />
                <span className="text-[10px] font-bold text-muted-foreground tracking-[0.2em] uppercase">Executive Summary</span>
              </div>
              <div className="relative p-5 rounded-2xl bg-muted/30 border border-border overflow-hidden group">
                <div className="absolute top-0 left-0 w-1 h-full bg-primary/40" />
                <p className="text-[13px] text-foreground leading-relaxed font-medium italic">
                  "{article.executive_summary}"
                </p>
              </div>
            </div>
          )}

          {/* Impact Analysis Section */}
          {article.impact_summary && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-amber-500 opacity-60 dark:text-amber-400" />
                <span className="text-[10px] font-bold text-muted-foreground tracking-[0.2em] uppercase">Market Impact</span>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed pl-1">
                {article.impact_summary}
              </p>
            </div>
          )}

          {/* Full Description */}
          {article.description && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-muted-foreground tracking-[0.2em] uppercase">Context</span>
              </div>
              <p className="text-[13px] text-muted-foreground leading-relaxed pl-1 font-serif opacity-90">
                {article.description}
              </p>
            </div>
          )}

          {/* Affected Symbols Section */}
          {article.affected_symbols.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Tag size={14} className="text-primary opacity-60" />
                <span className="text-[10px] font-bold text-muted-foreground tracking-[0.2em] uppercase">Affected Assets</span>
              </div>
              <div className="flex flex-wrap gap-2 pl-1">
                {article.affected_symbols.map((sym) => (
                  <div
                    key={sym}
                    className="flex items-center gap-2 bg-secondary hover:bg-muted border border-border px-3 py-1.5 rounded-lg transition-colors group cursor-default"
                  >
                    <span className="text-[11px] font-bold text-primary tracking-wider">${sym}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* History & Meta Section */}
          <div className="pt-8 border-t border-border space-y-6">
             <div className="grid grid-cols-2 gap-4">
               <div className="p-4 rounded-xl bg-muted/20 border border-border">
                 <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Published At</p>
                 <p className="text-xs text-muted-foreground font-mono">
                   {pubDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                   <span className="mx-2 text-border">·</span>
                   {pubDate.toLocaleDateString([], { month: 'short', day: 'numeric' })}
                 </p>
               </div>
               <div className="p-4 rounded-xl bg-muted/20 border border-border">
                 <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Analyzed At</p>
                 <p className="text-xs text-muted-foreground font-mono">
                   {analyzedDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                   <span className="mx-2 text-border">·</span>
                   {analyzedDate.toLocaleDateString([], { month: 'short', day: 'numeric' })}
                 </p>
               </div>
             </div>

             <div className="flex items-center justify-between px-2">
               <div className="flex items-center gap-2">
                 <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Article ID</span>
                 <span className="text-[9px] font-mono text-muted-foreground truncate max-w-[120px]">{article.id}</span>
               </div>
               <button 
                onClick={copyId}
                className="p-2 hover:bg-muted rounded-md transition-colors text-muted-foreground hover:text-foreground"
               >
                 {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
               </button>
             </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ── Compact card (dashboard/grouping) ────────────────────────────────────────
function CompactCard({ article, idx }: { article: NewsArticleRef; idx: number }) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const impact = getImpactLevel(article.impact_score);
  const pubDate = msToDate(article.published_at);

  return (
    <>
      <div
        className="bg-card border border-border rounded-xl p-3.5 flex items-start gap-4 hover:border-primary/50 hover:shadow-subtle transition-all cursor-pointer group active:scale-[0.98]"
        onClick={() => setSheetOpen(true)}
      >
        <div className={cn(
          "w-1 h-10 rounded-full shrink-0 mt-0.5",
          impact === 'high' ? "bg-red-500/40" : impact === 'medium' ? "bg-amber-500/40" : "bg-muted-foreground/20"
        )} />

        <div className="flex-1 min-w-0 space-y-1.5">
          <p className="text-xs text-foreground font-semibold leading-snug line-clamp-2 group-hover:text-primary transition-colors">
            {article.title}
          </p>
          <div className="flex items-center gap-3">
             <div className="flex items-center gap-1.5">
               <Badge variant="outline" className={cn("px-1.5 py-0 text-[9px] border-0 h-4 font-bold", IMPACT_SCORE_STYLES[impact])}>
                 {article.impact_score.toFixed(1)}
               </Badge>
             </div>
            <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">{article.source}</span>
            <span className="text-border">·</span>
            <span className="font-mono text-[10px] text-muted-foreground/60">{timeAgo(pubDate)}</span>
          </div>
        </div>
      </div>

      <ArticleDetailSheet article={article} idx={idx} open={sheetOpen} onOpenChange={setSheetOpen} />
    </>
  );
}

// ── Full card (main feed) ─────────────────────────────────────────────────────
function FullCard({ article, idx }: { article: NewsArticleRef; idx: number }) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const impact = getImpactLevel(article.impact_score);
  const pubDate = msToDate(article.published_at);

  return (
    <>
      <div className="bg-card border border-border rounded-2xl p-5 space-y-4 hover:border-primary/30 transition-all group relative overflow-hidden shadow-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn("px-2 py-0.5 text-[10px] font-bold tracking-widest border-0", IMPACT_SCORE_STYLES[impact])}
            >
              {impact.toUpperCase()} {article.impact_score.toFixed(1)}
            </Badge>
            <span className="text-muted-foreground font-mono text-[10px] uppercase tracking-wider">{timeAgo(pubDate)}</span>
          </div>
          
          <Badge
            variant="outline"
            className={cn(
              "px-2 py-0.5 text-[9px] font-bold tracking-wider border-0",
              STATUS_STYLES[article.processing_status]
            )}
          >
            {statusLabel(article.processing_status)}
          </Badge>
        </div>

        <div className="space-y-2">
          <h3 className="text-base font-bold text-foreground leading-snug line-clamp-2 group-hover:text-primary transition-colors">
            {article.title}
          </h3>
          <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 italic">
            {article.executive_summary}
          </p>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-border">
          <span className="font-mono text-[10px] text-muted-foreground tracking-wider">{article.source.toUpperCase()}</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-4 bg-secondary hover:bg-muted text-[10px] font-bold text-foreground tracking-widest rounded-lg transition-all"
            onClick={() => setSheetOpen(true)}
          >
            ANALYSIS
          </Button>
        </div>
      </div>

      <ArticleDetailSheet article={article} idx={idx} open={sheetOpen} onOpenChange={setSheetOpen} />
    </>
  );
}

// ── Public API ────────────────────────────────────────────────────────────────
interface NewsArticleCardProps {
  article: NewsArticleRef;
  idx?: number;
  compact?: boolean;
}

export function NewsArticleCard({ article, idx = 0, compact = false }: NewsArticleCardProps) {
  if (compact) return <CompactCard article={article} idx={idx} />;
  return <FullCard article={article} idx={idx} />;
}
