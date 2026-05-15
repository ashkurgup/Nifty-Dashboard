import React, { useState } from "react";
import { useGetPortfolioBySymbol } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCurrency, formatNumber } from "@/lib/utils";

type SortField = "symbol" | "realizedPnl" | "netQuantity" | "tradeCount";
type SortDirection = "asc" | "desc";

export default function Portfolio() {
  const { data: portfolio, isLoading } = useGetPortfolioBySymbol();
  const [sortField, setSortField] = useState<SortField>("realizedPnl");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const sortedPortfolio = React.useMemo(() => {
    if (!portfolio) return [];
    return [...portfolio].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }
      return 0;
    });
  }, [portfolio, sortField, sortDirection]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 h-full flex flex-col">
      <div className="flex flex-col gap-1 shrink-0">
        <h1 className="text-2xl font-bold font-mono uppercase tracking-tight">Portfolio</h1>
        <p className="text-muted-foreground text-sm">Positions and P&L breakdown by symbol.</p>
      </div>

      <Card className="border-border bg-card shadow-none flex-1 flex flex-col overflow-hidden">
        <CardHeader className="py-4 border-b border-border shrink-0 bg-muted/5">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-mono text-muted-foreground">Positions</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="p-0 overflow-auto flex-1">
          <Table>
            <TableHeader className="sticky top-0 bg-muted/5 backdrop-blur z-10 shadow-sm border-b border-border">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-[100px] cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort("symbol")}>
                  Symbol {sortField === "symbol" && (sortDirection === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead>Asset Type</TableHead>
                <TableHead className="text-right cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort("netQuantity")}>
                  Net Qty {sortField === "netQuantity" && (sortDirection === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead className="text-right">Avg Price</TableHead>
                <TableHead className="text-right cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort("realizedPnl")}>
                  Realized P&L {sortField === "realizedPnl" && (sortDirection === "asc" ? "↑" : "↓")}
                </TableHead>
                <TableHead className="text-right cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort("tradeCount")}>
                  Trades {sortField === "tradeCount" && (sortDirection === "asc" ? "↑" : "↓")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, idx) => (
                  <TableRow key={idx}>
                    <TableCell colSpan={6} className="h-12 bg-muted/10 animate-pulse" />
                  </TableRow>
                ))
              ) : sortedPortfolio.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    No positions found.
                  </TableCell>
                </TableRow>
              ) : (
                sortedPortfolio.map((pos) => (
                  <TableRow key={pos.symbol} className="hover:bg-muted/5 border-b border-border/50 transition-colors">
                    <TableCell className="font-bold font-mono">{pos.symbol}</TableCell>
                    <TableCell className="text-xs text-muted-foreground uppercase">{pos.assetType}</TableCell>
                    <TableCell className="text-right font-mono">{formatNumber(pos.netQuantity)}</TableCell>
                    <TableCell className="text-right font-mono">{formatCurrency(pos.avgBuyPrice)}</TableCell>
                    <TableCell className={`text-right font-mono font-bold ${pos.realizedPnl > 0 ? 'text-positive' : pos.realizedPnl < 0 ? 'text-negative' : ''}`}>
                      {pos.realizedPnl > 0 ? '+' : ''}{formatCurrency(pos.realizedPnl)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">{pos.tradeCount}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
