import { Router } from "express";
import { db, tradesTable } from "@workspace/db";
import { desc } from "drizzle-orm";

const router = Router();

router.get("/portfolio/summary", async (_req, res) => {
  const trades = await db.select().from(tradesTable).orderBy(desc(tradesTable.tradedAt));

  const totalTrades = trades.length;
  const totalBuys = trades.filter((t) => t.tradeType === "buy").length;
  const totalSells = trades.filter((t) => t.tradeType === "sell").length;

  const totalInvested = trades
    .filter((t) => t.tradeType === "buy")
    .reduce((sum, t) => sum + Number(t.quantity) * Number(t.price) + (t.fees ? Number(t.fees) : 0), 0);

  const totalProceeds = trades
    .filter((t) => t.tradeType === "sell")
    .reduce((sum, t) => sum + Number(t.quantity) * Number(t.price) - (t.fees ? Number(t.fees) : 0), 0);

  const realizedPnl = totalProceeds - totalInvested;

  // Compute per-symbol P&L for win rate
  const symbolMap = buildSymbolMap(trades);
  const symbolPnls = Object.values(symbolMap).map((s) => s.realizedPnl);
  const profitableSymbols = symbolPnls.filter((p) => p > 0).length;
  const winRate = symbolPnls.length > 0 ? (profitableSymbols / symbolPnls.length) * 100 : 0;

  const bestTrade = symbolPnls.length > 0 ? Math.max(...symbolPnls) : null;
  const worstTrade = symbolPnls.length > 0 ? Math.min(...symbolPnls) : null;

  res.json({
    totalTrades,
    totalBuys,
    totalSells,
    totalInvested,
    totalProceeds,
    realizedPnl,
    winRate,
    bestTrade,
    worstTrade,
  });
});

router.get("/portfolio/by-symbol", async (_req, res) => {
  const trades = await db.select().from(tradesTable).orderBy(desc(tradesTable.tradedAt));
  const symbolMap = buildSymbolMap(trades);

  const result = Object.values(symbolMap).sort((a, b) => b.realizedPnl - a.realizedPnl);
  res.json(result);
});

router.get("/portfolio/recent-activity", async (_req, res) => {
  const trades = await db.select().from(tradesTable).orderBy(desc(tradesTable.tradedAt)).limit(10);
  res.json(
    trades.map((t) => ({
      id: t.id,
      symbol: t.symbol,
      assetType: t.assetType,
      tradeType: t.tradeType,
      quantity: Number(t.quantity),
      price: Number(t.price),
      fees: t.fees != null ? Number(t.fees) : null,
      notes: t.notes,
      tradedAt: t.tradedAt instanceof Date ? t.tradedAt.toISOString() : t.tradedAt,
      createdAt: t.createdAt instanceof Date ? t.createdAt.toISOString() : t.createdAt,
    }))
  );
});

type TradeRow = typeof tradesTable.$inferSelect;

function buildSymbolMap(trades: TradeRow[]) {
  const map: Record<string, {
    symbol: string;
    assetType: string;
    totalBought: number;
    totalSold: number;
    netQuantity: number;
    avgBuyPrice: number;
    realizedPnl: number;
    tradeCount: number;
    totalBuyQty: number;
    totalBuyCost: number;
  }> = {};

  for (const trade of trades) {
    const sym = trade.symbol;
    if (!map[sym]) {
      map[sym] = {
        symbol: sym,
        assetType: trade.assetType,
        totalBought: 0,
        totalSold: 0,
        netQuantity: 0,
        avgBuyPrice: 0,
        realizedPnl: 0,
        tradeCount: 0,
        totalBuyQty: 0,
        totalBuyCost: 0,
      };
    }
    const entry = map[sym];
    const qty = Number(trade.quantity);
    const price = Number(trade.price);
    const fees = trade.fees ? Number(trade.fees) : 0;

    entry.tradeCount++;

    if (trade.tradeType === "buy") {
      entry.totalBought += qty * price + fees;
      entry.totalBuyQty += qty;
      entry.totalBuyCost += qty * price + fees;
      entry.netQuantity += qty;
      entry.avgBuyPrice = entry.totalBuyQty > 0 ? entry.totalBuyCost / entry.totalBuyQty : 0;
    } else {
      entry.totalSold += qty * price - fees;
      entry.netQuantity -= qty;
      const costBasis = entry.avgBuyPrice * qty;
      entry.realizedPnl += qty * price - fees - costBasis;
    }
  }

  return map;
}

export default router;
