import { NewsArticleCard } from "@/components/NewsArticleCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useNewsGrouped, useTriggerFetch } from "@/hooks/useNewsItems";
import { cn, timeAgo } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Newspaper, RefreshCw, LayoutGrid, Tag } from "lucide-react";
import { msToDate } from "@/types/trading";

export function GroupingPage() {
  const { data: groupedNews, isLoading, error } = useNewsGrouped();
  const triggerFetch = useTriggerFetch();

  const symbols = groupedNews ? Object.keys(groupedNews).sort() : [];

  return (
    <div className="flex flex-col h-full" data-ocid="grouping_page">
      <div className="flex-1 overflow-y-auto">
        <div className="px-5 pb-8 pt-4">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <div className="bg-primary/10 p-2 rounded-lg">
                <LayoutGrid size={18} className="text-primary" />
              </div>
              <div>
                <h1 className="text-lg font-bold tracking-tight">Stock Grouping</h1>
                <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                  News Intel Organized by Asset
                </p>
              </div>
            </div>

            <Button
              variant="outline"
              size="sm"
              className="h-8 font-mono text-[10px] border-border bg-background/50 backdrop-blur-sm"
              onClick={() => triggerFetch.mutate()}
              disabled={triggerFetch.isPending}
            >
              <RefreshCw
                size={10}
                className={cn("mr-1.5", triggerFetch.isPending && "animate-spin")}
              />
              {triggerFetch.isPending ? "FETCHING..." : "FETCH UPDATES"}
            </Button>
          </div>

          {/* Groups */}
          <div className="space-y-8">
            {isLoading ? (
              [1, 2, 3].map((i) => (
                <div key={i} className="space-y-4">
                  <Skeleton className="h-6 w-32 rounded" />
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <Skeleton className="h-40 rounded" />
                    <Skeleton className="h-40 rounded" />
                    <Skeleton className="h-40 rounded" />
                  </div>
                </div>
              ))
            ) : error ? (
              <div className="bg-card border border-destructive/20 rounded-xl p-12 text-center space-y-4">
                <p className="font-mono text-sm text-destructive">Failed to load grouped news</p>
                <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
                  Retry
                </Button>
              </div>
            ) : symbols.length === 0 ? (
              <div className="bg-card border border-border border-dashed rounded-xl p-16 text-center space-y-4">
                <Newspaper size={40} className="mx-auto text-muted-foreground opacity-20" />
                <div className="space-y-1">
                  <p className="font-mono text-xs text-muted-foreground">No Grouped Articles Found</p>
                  <p className="text-[10px] text-muted-foreground opacity-60 max-w-[200px] mx-auto">
                    Articles must be fetched and analyzed before they appear here. Click 'Fetch Updates' to populate the database.
                  </p>
                </div>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="mt-4"
                  onClick={() => triggerFetch.mutate()}
                  disabled={triggerFetch.isPending}
                >
                  Fetch News Now
                </Button>
              </div>
            ) : (
              <div className="space-y-12 max-w-5xl mx-auto">
                {symbols.map((symbol) => (
                  <div 
                    key={symbol} 
                    className="bg-card/50 backdrop-blur-sm border border-border rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition-all group" 
                    data-ocid={`grouping_card.${symbol}`}
                  >
                    {/* Symbol Header Banner */}
                    <div className="bg-muted/30 px-6 py-4 border-b border-border flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20">
                          <Tag size={18} className="text-primary" />
                        </div>
                        <div>
                          <h2 className="text-base font-bold tracking-tight text-foreground">{symbol}</h2>
                          <p className="text-[10px] text-muted-foreground font-mono uppercase tracking-widest">
                            {groupedNews?.[symbol].length} Analysis Reports
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end">
                         <span className="text-[9px] text-muted-foreground font-mono uppercase tracking-tighter opacity-60">Latest Intel</span>
                         <span className="text-[10px] text-primary font-bold">{timeAgo(msToDate(groupedNews?.[symbol][0].published_at))}</span>
                      </div>
                    </div>

                    {/* Articles Feed - Clean List Inside the Card */}
                    <div className="p-6 space-y-4">
                      {groupedNews?.[symbol].map((article, idx) => (
                        <NewsArticleCard 
                          key={`${symbol}-${article.id}`} 
                          article={article} 
                          idx={idx} 
                          compact={true} 
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
