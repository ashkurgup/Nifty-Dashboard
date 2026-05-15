import React from "react";
import { useGetPortfolioSummary, useGetRecentActivity } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatNumber, formatPercentage, formatShortDate } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight, Activity, Clock } from "lucide-react";
import { Link } from "wouter";

export default function Dashboard() {
  const { data: summary, isLoading: isSummaryLoading } = useGetPortfolioSummary();
  const { data: recentActivity, isLoading: isActivityLoading } = useGetRecentActivity();

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold font-mono uppercase tracking-tight">Terminal Dashboard</h1>
        <p className="text-muted-foreground text-sm">Portfolio overview and recent activity.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Realized P&L"
          value={summary ? formatCurrency(summary.realizedPnl) : "-"}
          isLoading={isSummaryLoading}
          trend={summary?.realizedPnl ? (summary.realizedPnl >= 0 ? 'up' : 'down') : undefined}
          trendValue={summary?.realizedPnl ? formatCurrency(summary.realizedPnl) : undefined}
        />
        <StatCard
          title="Win Rate"
          value={summary ? formatPercentage(summary.winRate) : "-"}
          isLoading={isSummaryLoading}
        />
        <StatCard
          title="Total Trades"
          value={summary ? formatNumber(summary.totalTrades, 0) : "-"}
          isLoading={isSummaryLoading}
        />
        <StatCard
          title="Total Invested"
          value={summary ? formatCurrency(summary.totalInvested) : "-"}
          isLoading={isSummaryLoading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border-border bg-card shadow-none">
          <CardHeader className="pb-2 border-b border-border">
            <CardTitle className="text-sm font-mono flex items-center gap-2 text-muted-foreground">
              <Activity className="w-4 h-4" />
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isActivityLoading ? (
              <div className="p-4 space-y-4">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="h-10 bg-muted/20 animate-pulse rounded" />
                ))}
              </div>
            ) : recentActivity?.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground text-sm">
                No recent activity.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {recentActivity?.map((trade) => (
                  <div key={trade.id} className="p-4 flex items-center justify-between hover:bg-muted/5 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className={`w-2 h-2 rounded-full ${trade.tradeType === 'buy' ? 'bg-primary' : 'bg-destructive'}`} />
                      <div>
                        <div className="font-bold text-sm">{trade.symbol}</div>
                        <div className="text-xs text-muted-foreground uppercase">{trade.assetType}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-mono">
                        {trade.tradeType === 'buy' ? '+' : '-'}{formatNumber(trade.quantity)} @ {formatCurrency(trade.price)}
                      </div>
                      <div className="text-xs text-muted-foreground flex items-center justify-end gap-1">
                        <Clock className="w-3 h-3" />
                        {formatShortDate(trade.tradedAt)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="p-4 border-t border-border bg-muted/10 text-center">
              <Link href="/trades" className="text-xs text-primary hover:underline font-mono uppercase tracking-widest cursor-pointer">
                View All Trades →
              </Link>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-none">
          <CardHeader className="pb-2 border-b border-border">
            <CardTitle className="text-sm font-mono flex items-center gap-2 text-muted-foreground">
              Performance Extremes
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-6">
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Best Trade</div>
              <div className="text-2xl font-mono text-positive">
                {isSummaryLoading ? <div className="h-8 w-24 bg-muted/20 animate-pulse rounded" /> : summary?.bestTrade ? formatCurrency(summary.bestTrade) : "-"}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Worst Trade</div>
              <div className="text-2xl font-mono text-negative">
                {isSummaryLoading ? <div className="h-8 w-24 bg-muted/20 animate-pulse rounded" /> : summary?.worstTrade ? formatCurrency(summary.worstTrade) : "-"}
              </div>
            </div>
            <div className="pt-4 border-t border-border">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Buys</span>
                <span className="font-mono">{summary?.totalBuys || 0}</span>
              </div>
              <div className="flex justify-between text-sm mt-2">
                <span className="text-muted-foreground">Sells</span>
                <span className="font-mono">{summary?.totalSells || 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatCard({ title, value, isLoading, trend, trendValue }: { title: string, value: string, isLoading: boolean, trend?: 'up' | 'down', trendValue?: string }) {
  return (
    <Card className="border-border bg-card shadow-none relative overflow-hidden group hover:border-primary/50 transition-colors">
      <CardContent className="p-6">
        <div className="text-sm font-medium text-muted-foreground mb-2 flex items-center justify-between">
          {title}
        </div>
        <div className="flex items-baseline gap-2">
          {isLoading ? (
            <div className="h-8 w-32 bg-muted/20 animate-pulse rounded" />
          ) : (
            <div className="text-3xl font-bold font-mono tracking-tight">{value}</div>
          )}
        </div>
        {trend && !isLoading && (
          <div className={`text-xs font-mono mt-2 flex items-center gap-1 ${trend === 'up' ? 'text-positive' : 'text-negative'}`}>
            {trend === 'up' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
            {trendValue}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
