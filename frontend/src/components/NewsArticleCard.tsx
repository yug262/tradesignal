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
  high: "text-red-400 border-red-500/30 bg-red-500/10",
  medium: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  low: "text-slate-400 border-slate-500/30 bg-slate-500/10",
};

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, string> = {
  analyzed: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  candidate: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  no_trade: "text-slate-500 border-slate-700 bg-slate-800/50",
  new: "text-purple-400 border-purple-500/30 bg-purple-500/10",
  planned: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  processed: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  pending: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  skipped: "text-slate-500 border-slate-700 bg-slate-800/50",
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
        className="w-[520px] max-w-full bg-[#0a0a0b] border-l border-white/5 overflow-y-auto p-0 scrollbar-hide"
      >
        {/* Header Hero Section */}
        <div className="relative p-8 pb-6 border-b border-white/5 bg-gradient-to-b from-white/[0.02] to-transparent">
          <div className="flex items-center gap-3 mb-6">
            <Badge
              variant="outline"
              className={cn("px-2.5 py-0.5 text-[10px] font-bold tracking-wider rounded-md border-0", IMPACT_SCORE_STYLES[impact])}
            >
              IMPACT {article.impact_score.toFixed(1)}
            </Badge>
            <Badge
              variant="outline"
              className="px-2.5 py-0.5 text-[10px] font-medium tracking-wider bg-white/5 border-white/10 text-slate-400 rounded-md"
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

          <h2 className="text-xl font-bold text-white leading-tight mb-4 tracking-tight">
            {article.title}
          </h2>

          <div className="flex items-center gap-4 text-slate-500 font-mono text-[10px]">
            <div className="flex items-center gap-1.5">
              <Newspaper size={12} className="opacity-50" />
              <span>{article.source.toUpperCase()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Calendar size={12} className="opacity-50" />
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
                <span className="text-[10px] font-bold text-slate-500 tracking-[0.2em] uppercase">Executive Summary</span>
              </div>
              <div className="relative p-5 rounded-2xl bg-white/[0.02] border border-white/5 overflow-hidden group">
                <div className="absolute top-0 left-0 w-1 h-full bg-primary/40" />
                <p className="text-[13px] text-slate-200 leading-relaxed font-medium italic">
                  "{article.executive_summary}"
                </p>
              </div>
            </div>
          )}

          {/* Impact Analysis Section */}
          {article.impact_summary && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Activity size={14} className="text-amber-400 opacity-60" />
                <span className="text-[10px] font-bold text-slate-500 tracking-[0.2em] uppercase">Market Impact</span>
              </div>
              <p className="text-sm text-slate-400 leading-relaxed pl-1">
                {article.impact_summary}
              </p>
            </div>
          )}

          {/* Full Description */}
          {article.description && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-slate-500 tracking-[0.2em] uppercase">Context</span>
              </div>
              <p className="text-[13px] text-slate-500 leading-relaxed pl-1 font-serif opacity-80">
                {article.description}
              </p>
            </div>
          )}

          {/* Affected Symbols Section */}
          {article.affected_symbols.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Tag size={14} className="text-primary opacity-60" />
                <span className="text-[10px] font-bold text-slate-500 tracking-[0.2em] uppercase">Affected Assets</span>
              </div>
              <div className="flex flex-wrap gap-2 pl-1">
                {article.affected_symbols.map((sym) => (
                  <div
                    key={sym}
                    className="flex items-center gap-2 bg-white/[0.03] hover:bg-white/[0.06] border border-white/10 px-3 py-1.5 rounded-lg transition-colors group cursor-default"
                  >
                    <span className="text-[11px] font-bold text-primary tracking-wider">${sym}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* History & Meta Section */}
          <div className="pt-8 border-t border-white/5 space-y-6">
             <div className="grid grid-cols-2 gap-4">
               <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                 <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest mb-2">Published At</p>
                 <p className="text-xs text-slate-400 font-mono">
                   {pubDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                   <span className="mx-2 text-slate-700">·</span>
                   {pubDate.toLocaleDateString([], { month: 'short', day: 'numeric' })}
                 </p>
               </div>
               <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                 <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest mb-2">Analyzed At</p>
                 <p className="text-xs text-slate-400 font-mono">
                   {analyzedDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                   <span className="mx-2 text-slate-700">·</span>
                   {analyzedDate.toLocaleDateString([], { month: 'short', day: 'numeric' })}
                 </p>
               </div>
             </div>

             <div className="flex items-center justify-between px-2">
               <div className="flex items-center gap-2">
                 <span className="text-[9px] font-bold text-slate-700 uppercase tracking-widest">Article ID</span>
                 <span className="text-[9px] font-mono text-slate-600 truncate max-w-[120px]">{article.id}</span>
               </div>
               <button 
                onClick={copyId}
                className="p-2 hover:bg-white/5 rounded-md transition-colors text-slate-600 hover:text-slate-300"
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
        className="bg-card/30 backdrop-blur-sm border border-white/5 rounded-xl p-3.5 flex items-start gap-4 hover:border-primary/20 hover:bg-white/[0.02] transition-all cursor-pointer group active:scale-[0.98]"
        onClick={() => setSheetOpen(true)}
      >
        <div className={cn(
          "w-1 h-10 rounded-full shrink-0 mt-0.5",
          impact === 'high' ? "bg-red-500/40" : impact === 'medium' ? "bg-amber-500/40" : "bg-slate-500/40"
        )} />

        <div className="flex-1 min-w-0 space-y-1.5">
          <p className="text-xs text-slate-200 font-semibold leading-snug line-clamp-2 group-hover:text-white transition-colors">
            {article.title}
          </p>
          <div className="flex items-center gap-3">
             <div className="flex items-center gap-1.5">
               <Badge variant="outline" className={cn("px-1.5 py-0 text-[9px] border-0 h-4 font-bold", IMPACT_SCORE_STYLES[impact])}>
                 {article.impact_score.toFixed(1)}
               </Badge>
             </div>
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">{article.source}</span>
            <span className="text-slate-700">·</span>
            <span className="font-mono text-[10px] text-slate-600">{timeAgo(pubDate)}</span>
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
      <div className="bg-white/[0.01] backdrop-blur-md border border-white/5 rounded-2xl p-5 space-y-4 hover:border-white/10 transition-all group relative overflow-hidden">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn("px-2 py-0.5 text-[10px] font-bold tracking-widest border-0", IMPACT_SCORE_STYLES[impact])}
            >
              {impact.toUpperCase()} {article.impact_score.toFixed(1)}
            </Badge>
            <span className="text-slate-600 font-mono text-[10px]">{timeAgo(pubDate).toUpperCase()}</span>
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
          <h3 className="text-base font-bold text-slate-100 leading-snug line-clamp-2 group-hover:text-white transition-colors">
            {article.title}
          </h3>
          <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 italic">
            {article.executive_summary}
          </p>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-white/5">
          <span className="font-mono text-[10px] text-slate-600 tracking-wider">{article.source.toUpperCase()}</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-4 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-white tracking-widest rounded-lg transition-all"
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
