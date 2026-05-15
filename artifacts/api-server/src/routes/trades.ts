import { Router } from "express";
import { db, tradesTable, insertTradeSchema, updateTradeSchema } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import { ListTradesQueryParams, CreateTradeBody, GetTradeParams, UpdateTradeParams, UpdateTradeBody, DeleteTradeParams } from "@workspace/api-zod";

const router = Router();

router.get("/trades", async (req, res) => {
  const parsed = ListTradesQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const { symbol, assetType, tradeType } = parsed.data;

  let query = db.select().from(tradesTable).$dynamic();

  const conditions = [];
  if (symbol) conditions.push(eq(tradesTable.symbol, symbol.toUpperCase()));
  if (assetType) conditions.push(eq(tradesTable.assetType, assetType as "stock" | "crypto" | "options" | "forex" | "other"));
  if (tradeType) conditions.push(eq(tradesTable.tradeType, tradeType as "buy" | "sell"));

  if (conditions.length > 0) {
    const { and } = await import("drizzle-orm");
    query = query.where(and(...conditions));
  }

  const trades = await query.orderBy(desc(tradesTable.tradedAt));
  res.json(trades.map(serializeTrade));
});

router.post("/trades", async (req, res) => {
  const parsed = CreateTradeBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const body = parsed.data;
  const input = insertTradeSchema.parse({
    symbol: body.symbol,
    assetType: body.assetType,
    tradeType: body.tradeType,
    quantity: body.quantity,
    price: body.price,
    fees: body.fees ?? null,
    notes: body.notes ?? null,
    tradedAt: new Date(body.tradedAt),
  });

  const [trade] = await db.insert(tradesTable).values({
    symbol: input.symbol,
    assetType: input.assetType,
    tradeType: input.tradeType,
    quantity: String(input.quantity),
    price: String(input.price),
    fees: input.fees != null ? String(input.fees) : null,
    notes: input.notes ?? null,
    tradedAt: input.tradedAt as Date,
  }).returning();

  res.status(201).json(serializeTrade(trade));
});

router.get("/trades/:id", async (req, res) => {
  const parsed = GetTradeParams.safeParse({ id: Number(req.params.id) });
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }

  const [trade] = await db.select().from(tradesTable).where(eq(tradesTable.id, parsed.data.id));
  if (!trade) {
    res.status(404).json({ error: "Trade not found" });
    return;
  }
  res.json(serializeTrade(trade));
});

router.patch("/trades/:id", async (req, res) => {
  const paramsParsed = UpdateTradeParams.safeParse({ id: Number(req.params.id) });
  if (!paramsParsed.success) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }

  const bodyParsed = UpdateTradeBody.safeParse(req.body);
  if (!bodyParsed.success) {
    res.status(400).json({ error: bodyParsed.error.message });
    return;
  }

  const [existing] = await db.select().from(tradesTable).where(eq(tradesTable.id, paramsParsed.data.id));
  if (!existing) {
    res.status(404).json({ error: "Trade not found" });
    return;
  }

  const body = bodyParsed.data;
  const updateData = updateTradeSchema.parse({
    ...(body.symbol !== undefined && { symbol: body.symbol }),
    ...(body.assetType !== undefined && { assetType: body.assetType }),
    ...(body.tradeType !== undefined && { tradeType: body.tradeType }),
    ...(body.quantity !== undefined && { quantity: body.quantity }),
    ...(body.price !== undefined && { price: body.price }),
    ...(body.fees !== undefined && { fees: body.fees }),
    ...(body.notes !== undefined && { notes: body.notes }),
    ...(body.tradedAt !== undefined && { tradedAt: new Date(body.tradedAt) }),
  });

  const dbUpdate: Record<string, unknown> = {};
  if (updateData.symbol !== undefined) dbUpdate.symbol = updateData.symbol;
  if (updateData.assetType !== undefined) dbUpdate.assetType = updateData.assetType;
  if (updateData.tradeType !== undefined) dbUpdate.tradeType = updateData.tradeType;
  if (updateData.quantity !== undefined) dbUpdate.quantity = String(updateData.quantity);
  if (updateData.price !== undefined) dbUpdate.price = String(updateData.price);
  if (updateData.fees !== undefined) dbUpdate.fees = updateData.fees != null ? String(updateData.fees) : null;
  if (updateData.notes !== undefined) dbUpdate.notes = updateData.notes ?? null;
  if (updateData.tradedAt !== undefined) dbUpdate.tradedAt = updateData.tradedAt;

  const [updated] = await db.update(tradesTable).set(dbUpdate).where(eq(tradesTable.id, paramsParsed.data.id)).returning();
  res.json(serializeTrade(updated));
});

router.delete("/trades/:id", async (req, res) => {
  const parsed = DeleteTradeParams.safeParse({ id: Number(req.params.id) });
  if (!parsed.success) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }

  const [existing] = await db.select().from(tradesTable).where(eq(tradesTable.id, parsed.data.id));
  if (!existing) {
    res.status(404).json({ error: "Trade not found" });
    return;
  }

  await db.delete(tradesTable).where(eq(tradesTable.id, parsed.data.id));
  res.status(204).send();
});

function serializeTrade(trade: typeof tradesTable.$inferSelect) {
  return {
    id: trade.id,
    symbol: trade.symbol,
    assetType: trade.assetType,
    tradeType: trade.tradeType,
    quantity: Number(trade.quantity),
    price: Number(trade.price),
    fees: trade.fees != null ? Number(trade.fees) : null,
    notes: trade.notes,
    tradedAt: trade.tradedAt instanceof Date ? trade.tradedAt.toISOString() : trade.tradedAt,
    createdAt: trade.createdAt instanceof Date ? trade.createdAt.toISOString() : trade.createdAt,
  };
}

export default router;
