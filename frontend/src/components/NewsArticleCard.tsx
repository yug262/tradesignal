import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, timeAgo } from "@/lib/utils";
import { msToDate, getImpactLevel } from "@/types/trading";
import type { NewsArticleRef } from "@/types/trading";
import { Check, Copy, Tag, Calendar, Activity, Newspaper, Quote, ExternalLink, TrendingUp, TrendingDown, Target, Zap, Info, Layers, BarChart3 } from "lucide-react";
import { useState } from "react";

// ── Style Maps ──────────────────────────────────────────────────────────────
const IMPACT_SCORE_STYLES: Record<string, string> = {
  high: "text-red-500 border-red-500/30 bg-red-500/10 dark:text-red-400",
  medium: "text-amber-600 border-amber-500/30 bg-amber-500/10 dark:text-amber-400",
  low: "text-muted-foreground border-border bg-muted/50",
};

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

const BIAS_STYLES: Record<string, string> = {
  bullish: "text-emerald-500 border-emerald-500/30 bg-emerald-500/10",
  bearish: "text-red-500 border-red-500/30 bg-red-500/10",
  neutral: "text-muted-foreground border-border bg-muted/50",
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

// ── Shared Detail Dialog ──────────────────────────────────────────────────────
interface ArticleDetailProps {
  article: NewsArticleRef;
  idx: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function ArticleDetail({ article, idx, open, onOpenChange }: ArticleDetailProps) {
  const [copied, setCopied] = useState(false);
  const impact = getImpactLevel(article.impact_score ?? 0);
  const pubDate = msToDate(article.published_at);
  const analyzedDate = article.analyzed_at ? msToDate(article.analyzed_at) : null;

  function copyId() {
    navigator.clipboard.writeText(article.id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl p-0 overflow-hidden border-border bg-background shadow-2xl rounded-2xl">
        <ScrollArea className="max-h-[85vh] w-full">
          <div className="flex flex-col">
            {/* Header Section */}
            <div className="p-6 border-b border-border bg-muted/10 space-y-6">
            <div className="flex items-center gap-3">
              <Badge className={cn("px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border-0", IMPACT_SCORE_STYLES[impact])}>
                IMPACT {(article.impact_score ?? 0).toFixed(1)}
              </Badge>
              <Badge variant="outline" className="px-2 py-0.5 text-[10px] font-medium border-border text-muted-foreground">
                {article.news_category?.toUpperCase() || "GENERAL"}
              </Badge>
              <Badge className={cn("px-2 py-0.5 text-[10px] font-bold tracking-wider rounded border-0 ml-auto", STATUS_STYLES[article.processing_status])}>
                {statusLabel(article.processing_status)}
              </Badge>
            </div>

            <div className="flex items-start justify-between gap-4">
              <h2 className="text-xl font-bold text-foreground leading-snug tracking-tight flex-1">
                {article.title}
              </h2>
              {article.link && (
                <a 
                  href={article.link} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="p-2 hover:bg-muted rounded-lg transition-colors text-muted-foreground hover:text-primary"
                >
                  <ExternalLink size={18} />
                </a>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-4 text-muted-foreground font-mono text-[10px] font-bold opacity-80">
              <div className="flex items-center gap-1.5">
                <Newspaper size={12} className="opacity-70" />
                <span>{article.source.toUpperCase()}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Calendar size={12} className="opacity-70" />
                <span>{timeAgo(pubDate).toUpperCase()}</span>
              </div>
              {article.primary_symbol && (
                <div className="flex items-center gap-1.5 text-primary/80">
                  <Target size={12} />
                  <span>${article.primary_symbol.toUpperCase()}</span>
                </div>
              )}
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-3 gap-3 p-6 border-b border-border bg-muted/5">
             {/* Bias */}
             <div className={cn(
               "p-4 rounded-xl border flex flex-col gap-2",
               article.market_bias?.toLowerCase() === 'bullish' ? "bg-emerald-500/5 border-emerald-500/10" : 
               article.market_bias?.toLowerCase() === 'bearish' ? "bg-red-500/5 border-red-500/10" : 
               "bg-muted/30 border-border/50"
             )}>
                <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Market Bias</span>
                <div className="flex items-center gap-2">
                  {article.market_bias?.toLowerCase() === 'bullish' ? <TrendingUp size={14} className="text-emerald-500" /> : 
                   article.market_bias?.toLowerCase() === 'bearish' ? <TrendingDown size={14} className="text-red-500" /> : 
                   <Activity size={14} className="text-muted-foreground" />}
                  <span className={cn("text-xs font-bold uppercase", 
                    article.market_bias?.toLowerCase() === 'bullish' ? "text-emerald-500" : 
                    article.market_bias?.toLowerCase() === 'bearish' ? "text-red-500" : "text-muted-foreground"
                  )}>
                    {article.market_bias || 'NEUTRAL'}
                  </span>
                </div>
             </div>

             {/* Horizon */}
             <div className="p-4 rounded-xl bg-muted/30 border border-border/50 flex flex-col gap-2">
                <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Horizon</span>
                <div className="flex items-center gap-2 text-foreground">
                  <Target size={14} className="opacity-60" />
                  <span className="text-xs font-bold uppercase">
                    {(article.horizon || 'SHORT_TERM').replace('_', ' ')}
                  </span>
                </div>
             </div>

             {/* Confidence */}
             <div className="p-4 rounded-xl bg-muted/30 border border-border/50 flex flex-col gap-2">
                <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">AI Confidence</span>
                <div className="flex items-center gap-2">
                  <Zap size={14} className="text-amber-500" />
                  <span className="text-xs font-bold text-foreground">{article.confidence ?? 0}%</span>
                </div>
                <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
                   <div 
                     className="h-full bg-amber-500 rounded-full" 
                     style={{ width: `${article.confidence ?? 0}%` }}
                   />
                </div>
             </div>
          </div>

          {/* Content Body */}
          <div className="p-6 space-y-8">
            {/* Executive Intelligence */}
            {article.executive_summary && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Quote size={14} className="text-primary opacity-60" />
                  <span className="text-[10px] font-bold text-muted-foreground tracking-widest uppercase">Executive Summary</span>
                </div>
                <div className="relative p-5 rounded-xl bg-primary/5 border border-primary/10">
                  <p className="text-sm text-foreground leading-relaxed font-medium italic">
                    "{article.executive_summary}"
                  </p>
                </div>
              </div>
            )}

            {/* Strategic Rationale */}
            {article.news_reason && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Info size={14} className="text-amber-500 opacity-60" />
                  <span className="text-[10px] font-bold text-muted-foreground tracking-widest uppercase">Analysis Reasoning</span>
                </div>
                <div className="p-5 rounded-xl bg-muted/20 border border-border text-sm text-muted-foreground leading-relaxed">
                  {article.news_reason}
                </div>
              </div>
            )}

            {/* Market Context */}
            {article.description && (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Layers size={14} className="text-muted-foreground opacity-60" />
                  <span className="text-[10px] font-bold text-muted-foreground tracking-widest uppercase">Original News</span>
                </div>
                <p className="text-[13px] text-muted-foreground leading-relaxed font-serif opacity-90 pl-3 border-l-2 border-border/50">
                  {article.description}
                </p>
              </div>
            )}

            {/* Impacted Entities */}
            {(article.affected_symbols.length > 0 || (article.affected_sectors && article.affected_sectors.length > 0)) && (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <Tag size={14} className="text-primary opacity-60" />
                  <span className="text-[10px] font-bold text-muted-foreground tracking-widest uppercase">Affected Entities</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {article.affected_symbols.map((sym) => (
                    <div
                      key={sym}
                      className="bg-secondary/50 border border-border px-3 py-1.5 rounded-lg text-[11px] font-bold text-primary"
                    >
                      ${sym}
                    </div>
                  ))}
                  {article.affected_sectors && article.affected_sectors.map((sector) => (
                    <div
                      key={sector}
                      className="bg-muted px-3 py-1.5 border border-border/50 rounded-lg text-[11px] font-medium text-muted-foreground"
                    >
                      {sector}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Footer Metadata */}
            <div className="pt-6 border-t border-border grid grid-cols-2 gap-6">
               <div className="space-y-1">
                 <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Published</p>
                 <p className="text-xs text-foreground font-semibold">
                   {pubDate.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })} · {pubDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                 </p>
               </div>
               <div className="space-y-1 text-right">
                 <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">System Sync</p>
                 <p className="text-xs text-foreground font-semibold">
                   {analyzedDate ? analyzedDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '---'}
                 </p>
               </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-muted/30 rounded-lg border border-border/50">
              <div className="flex items-center gap-2">
                <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Article ID</span>
                <span className="text-[9px] font-mono text-muted-foreground/60">{article.id}</span>
              </div>
              <button 
                onClick={copyId}
                className="p-1.5 hover:bg-background rounded-md transition-colors text-muted-foreground hover:text-foreground"
              >
                {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
              </button>
            </div>
          </div>
        </div>
      </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

// ── Compact card (dashboard/grouping) ────────────────────────────────────────
function CompactCard({ article, idx }: { article: NewsArticleRef; idx: number }) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const impact = getImpactLevel(article.impact_score ?? 0);
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
                 {(article.impact_score ?? 0).toFixed(1)}
               </Badge>
             </div>
            <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">{article.source}</span>
            <span className="text-border">·</span>
            <span className="font-mono text-[10px] text-muted-foreground/60">{timeAgo(pubDate)}</span>
          </div>
        </div>
      </div>

      <ArticleDetail article={article} idx={idx} open={sheetOpen} onOpenChange={setSheetOpen} />
    </>
  );
}

// ── Full card (main feed) ─────────────────────────────────────────────────────
function FullCard({ article, idx }: { article: NewsArticleRef; idx: number }) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const impact = getImpactLevel(article.impact_score ?? 0);
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
              {impact.toUpperCase()} {(article.impact_score ?? 0).toFixed(1)}
            </Badge>
            {article.market_bias && (
              <Badge
                variant="outline"
                className={cn("px-2 py-0.5 text-[9px] font-bold tracking-wider border-0 uppercase", BIAS_STYLES[article.market_bias.toLowerCase() as keyof typeof BIAS_STYLES] || BIAS_STYLES.neutral)}
              >
                {article.market_bias}
              </Badge>
            )}
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

      <ArticleDetail article={article} idx={idx} open={sheetOpen} onOpenChange={setSheetOpen} />
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
