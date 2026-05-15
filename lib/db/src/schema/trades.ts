import { pgTable, serial, text, numeric, timestamp, pgEnum } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const assetTypeEnum = pgEnum("asset_type", ["stock", "crypto", "options", "forex", "other"]);
export const tradeTypeEnum = pgEnum("trade_type", ["buy", "sell"]);

export const tradesTable = pgTable("trades", {
  id: serial("id").primaryKey(),
  symbol: text("symbol").notNull(),
  assetType: assetTypeEnum("asset_type").notNull(),
  tradeType: tradeTypeEnum("trade_type").notNull(),
  quantity: numeric("quantity", { precision: 18, scale: 8 }).notNull(),
  price: numeric("price", { precision: 18, scale: 8 }).notNull(),
  fees: numeric("fees", { precision: 18, scale: 8 }),
  notes: text("notes"),
  tradedAt: timestamp("traded_at", { withTimezone: true }).notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertTradeSchema = createInsertSchema(tradesTable).omit({ id: true, createdAt: true }).extend({
  symbol: z.string().min(1).transform((s) => s.toUpperCase().trim()),
  quantity: z.coerce.number().positive(),
  price: z.coerce.number().positive(),
  fees: z.coerce.number().nonnegative().optional(),
  tradedAt: z.coerce.date(),
});

export const updateTradeSchema = insertTradeSchema.partial();

export type InsertTrade = z.infer<typeof insertTradeSchema>;
export type UpdateTrade = z.infer<typeof updateTradeSchema>;
export type Trade = typeof tradesTable.$inferSelect;
