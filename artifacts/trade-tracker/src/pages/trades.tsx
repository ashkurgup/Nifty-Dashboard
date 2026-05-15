import React, { useState } from "react";
import { useListTrades, useCreateTrade, useUpdateTrade, useDeleteTrade, getListTradesQueryKey } from "@workspace/api-client-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Pencil, Trash2, Search, X } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { formatCurrency, formatNumber, formatDate } from "@/lib/utils";

const tradeFormSchema = z.object({
  symbol: z.string().min(1, "Symbol is required"),
  assetType: z.enum(["stock", "crypto", "options", "forex", "other"]),
  tradeType: z.enum(["buy", "sell"]),
  quantity: z.coerce.number().positive("Must be positive"),
  price: z.coerce.number().positive("Must be positive"),
  fees: z.coerce.number().nonnegative().optional(),
  notes: z.string().optional(),
  tradedAt: z.string().min(1, "Date is required"),
});

type TradeFormValues = z.infer<typeof tradeFormSchema>;

type Trade = {
  id: number;
  symbol: string;
  assetType: string;
  tradeType: string;
  quantity: number;
  price: number;
  fees: number | null;
  notes: string | null;
  tradedAt: string;
  createdAt: string;
};

export default function Trades() {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingTrade, setDeletingTrade] = useState<Trade | null>(null);
  const [searchSymbol, setSearchSymbol] = useState("");
  const [filterAssetType, setFilterAssetType] = useState<string>("all");
  const [filterTradeType, setFilterTradeType] = useState<string>("all");

  const queryClient = useQueryClient();
  const { toast } = useToast();

  const queryParams = {
    ...(searchSymbol ? { symbol: searchSymbol.toUpperCase() } : {}),
    ...(filterAssetType !== "all" ? { assetType: filterAssetType } : {}),
    ...(filterTradeType !== "all" ? { tradeType: filterTradeType } : {}),
  };

  const { data: trades, isLoading } = useListTrades(queryParams);
  const createTrade = useCreateTrade();
  const updateTrade = useUpdateTrade();
  const deleteTrade = useDeleteTrade();

  const form = useForm<TradeFormValues>({
    resolver: zodResolver(tradeFormSchema),
    defaultValues: {
      symbol: "",
      assetType: "stock",
      tradeType: "buy",
      quantity: 0,
      price: 0,
      fees: 0,
      notes: "",
      tradedAt: new Date().toISOString().slice(0, 16),
    },
  });

  function openAddSheet() {
    setEditingTrade(null);
    form.reset({
      symbol: "",
      assetType: "stock",
      tradeType: "buy",
      quantity: 0,
      price: 0,
      fees: 0,
      notes: "",
      tradedAt: new Date().toISOString().slice(0, 16),
    });
    setSheetOpen(true);
  }

  function openEditSheet(trade: Trade) {
    setEditingTrade(trade);
    form.reset({
      symbol: trade.symbol,
      assetType: trade.assetType as TradeFormValues["assetType"],
      tradeType: trade.tradeType as TradeFormValues["tradeType"],
      quantity: trade.quantity,
      price: trade.price,
      fees: trade.fees ?? 0,
      notes: trade.notes ?? "",
      tradedAt: new Date(trade.tradedAt).toISOString().slice(0, 16),
    });
    setSheetOpen(true);
  }

  function onSubmit(values: TradeFormValues) {
    const payload = {
      symbol: values.symbol.toUpperCase(),
      assetType: values.assetType,
      tradeType: values.tradeType,
      quantity: values.quantity,
      price: values.price,
      fees: values.fees,
      notes: values.notes || undefined,
      tradedAt: new Date(values.tradedAt).toISOString(),
    };

    if (editingTrade) {
      updateTrade.mutate(
        { id: editingTrade.id, data: payload },
        {
          onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: getListTradesQueryKey() });
            setSheetOpen(false);
            toast({ title: "Trade updated" });
          },
          onError: () => toast({ title: "Failed to update trade", variant: "destructive" }),
        }
      );
    } else {
      createTrade.mutate(
        { data: payload },
        {
          onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: getListTradesQueryKey() });
            setSheetOpen(false);
            toast({ title: "Trade added" });
          },
          onError: () => toast({ title: "Failed to add trade", variant: "destructive" }),
        }
      );
    }
  }

  function confirmDelete(trade: Trade) {
    setDeletingTrade(trade);
    setDeleteDialogOpen(true);
  }

  function handleDelete() {
    if (!deletingTrade) return;
    deleteTrade.mutate(
      { id: deletingTrade.id },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: getListTradesQueryKey() });
          setDeleteDialogOpen(false);
          setDeletingTrade(null);
          toast({ title: "Trade deleted" });
        },
        onError: () => toast({ title: "Failed to delete trade", variant: "destructive" }),
      }
    );
  }

  const hasFilters = searchSymbol || filterAssetType !== "all" || filterTradeType !== "all";

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 h-full flex flex-col">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-bold font-mono uppercase tracking-tight">Trade Log</h1>
          <p className="text-muted-foreground text-sm mt-1">All your trades, filterable and sortable.</p>
        </div>
        <Button onClick={openAddSheet} data-testid="button-add-trade" className="gap-2">
          <Plus className="w-4 h-4" />
          Add Trade
        </Button>
      </div>

      <div className="flex flex-wrap gap-3 shrink-0">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Filter by symbol..."
            value={searchSymbol}
            onChange={(e) => setSearchSymbol(e.target.value)}
            className="pl-9 font-mono"
            data-testid="input-search-symbol"
          />
        </div>
        <Select value={filterAssetType} onValueChange={setFilterAssetType}>
          <SelectTrigger className="w-[140px]" data-testid="select-asset-type-filter">
            <SelectValue placeholder="Asset type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            <SelectItem value="stock">Stock</SelectItem>
            <SelectItem value="crypto">Crypto</SelectItem>
            <SelectItem value="options">Options</SelectItem>
            <SelectItem value="forex">Forex</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filterTradeType} onValueChange={setFilterTradeType}>
          <SelectTrigger className="w-[120px]" data-testid="select-trade-type-filter">
            <SelectValue placeholder="Buy/Sell" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Buy &amp; Sell</SelectItem>
            <SelectItem value="buy">Buys only</SelectItem>
            <SelectItem value="sell">Sells only</SelectItem>
          </SelectContent>
        </Select>
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={() => { setSearchSymbol(""); setFilterAssetType("all"); setFilterTradeType("all"); }} className="gap-1 text-muted-foreground">
            <X className="w-3 h-3" /> Clear
          </Button>
        )}
      </div>

      <Card className="border-border bg-card shadow-none flex-1 flex flex-col overflow-hidden">
        <CardHeader className="py-3 border-b border-border shrink-0 bg-muted/5">
          <CardTitle className="text-xs font-mono text-muted-foreground uppercase tracking-widest">
            {isLoading ? "Loading..." : `${trades?.length ?? 0} trades`}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0 overflow-auto flex-1">
          <Table>
            <TableHeader className="sticky top-0 bg-card z-10 border-b border-border">
              <TableRow className="hover:bg-transparent">
                <TableHead className="font-mono text-xs">Symbol</TableHead>
                <TableHead className="font-mono text-xs">Type</TableHead>
                <TableHead className="text-right font-mono text-xs">Qty</TableHead>
                <TableHead className="text-right font-mono text-xs">Price</TableHead>
                <TableHead className="text-right font-mono text-xs">Total</TableHead>
                <TableHead className="text-right font-mono text-xs">Fees</TableHead>
                <TableHead className="font-mono text-xs">Date</TableHead>
                <TableHead className="font-mono text-xs">Notes</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 9 }).map((_, j) => (
                      <TableCell key={j}><div className="h-4 bg-muted/20 animate-pulse rounded w-full" /></TableCell>
                    ))}
                  </TableRow>
                ))
              ) : !trades || trades.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-16 text-muted-foreground">
                    <div className="space-y-2">
                      <div className="font-mono text-xs uppercase tracking-widest">No trades found</div>
                      {hasFilters ? (
                        <div className="text-xs">Try clearing your filters</div>
                      ) : (
                        <div className="text-xs">Add your first trade to get started</div>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                trades.map((trade) => (
                  <TableRow
                    key={trade.id}
                    className="hover:bg-muted/5 border-b border-border/50 transition-colors group"
                    data-testid={`row-trade-${trade.id}`}
                  >
                    <TableCell className="font-bold font-mono">
                      <div>{trade.symbol}</div>
                      <div className="text-xs text-muted-foreground uppercase">{trade.assetType}</div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={trade.tradeType === "buy"
                          ? "border-primary/40 text-primary bg-primary/10 font-mono text-xs uppercase"
                          : "border-destructive/40 text-destructive bg-destructive/10 font-mono text-xs uppercase"
                        }
                        data-testid={`badge-trade-type-${trade.id}`}
                      >
                        {trade.tradeType}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">{formatNumber(trade.quantity)}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{formatCurrency(trade.price)}</TableCell>
                    <TableCell className="text-right font-mono text-sm font-medium">
                      {formatCurrency(trade.quantity * trade.price)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm text-muted-foreground">
                      {trade.fees ? formatCurrency(trade.fees) : "-"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground font-mono whitespace-nowrap">
                      {formatDate(trade.tradedAt)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[160px] truncate">
                      {trade.notes || "-"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => openEditSheet(trade as Trade)}
                          data-testid={`button-edit-trade-${trade.id}`}
                        >
                          <Pencil className="w-3 h-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive hover:text-destructive"
                          onClick={() => confirmDelete(trade as Trade)}
                          data-testid={`button-delete-trade-${trade.id}`}
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader className="mb-6">
            <SheetTitle className="font-mono uppercase tracking-tight">
              {editingTrade ? "Edit Trade" : "Add Trade"}
            </SheetTitle>
          </SheetHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="symbol"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-xs font-mono uppercase">Symbol</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder="AAPL" className="font-mono uppercase" data-testid="input-symbol" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="assetType"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-xs font-mono uppercase">Asset Type</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger data-testid="select-asset-type">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="stock">Stock</SelectItem>
                          <SelectItem value="crypto">Crypto</SelectItem>
                          <SelectItem value="options">Options</SelectItem>
                          <SelectItem value="forex">Forex</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="tradeType"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs font-mono uppercase">Trade Type</FormLabel>
                    <div className="flex gap-2">
                      {(["buy", "sell"] as const).map((type) => (
                        <button
                          key={type}
                          type="button"
                          onClick={() => field.onChange(type)}
                          className={`flex-1 py-2 text-sm font-mono uppercase tracking-wider border transition-colors ${
                            field.value === type
                              ? type === "buy"
                                ? "bg-primary/10 border-primary text-primary"
                                : "bg-destructive/10 border-destructive text-destructive"
                              : "border-border text-muted-foreground hover:border-foreground/30"
                          }`}
                          data-testid={`button-trade-type-${type}`}
                        >
                          {type}
                        </button>
                      ))}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="quantity"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-xs font-mono uppercase">Quantity</FormLabel>
                      <FormControl>
                        <Input {...field} type="number" step="any" placeholder="0" className="font-mono" data-testid="input-quantity" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="price"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="text-xs font-mono uppercase">Price</FormLabel>
                      <FormControl>
                        <Input {...field} type="number" step="any" placeholder="0.00" className="font-mono" data-testid="input-price" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="fees"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs font-mono uppercase">Fees (optional)</FormLabel>
                    <FormControl>
                      <Input {...field} type="number" step="any" placeholder="0.00" className="font-mono" data-testid="input-fees" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="tradedAt"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs font-mono uppercase">Date &amp; Time</FormLabel>
                    <FormControl>
                      <Input {...field} type="datetime-local" className="font-mono" data-testid="input-traded-at" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="notes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs font-mono uppercase">Notes (optional)</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="Trade rationale..." data-testid="input-notes" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button
                type="submit"
                className="w-full font-mono uppercase tracking-wider"
                disabled={createTrade.isPending || updateTrade.isPending}
                data-testid="button-submit-trade"
              >
                {createTrade.isPending || updateTrade.isPending ? "Saving..." : editingTrade ? "Save Changes" : "Add Trade"}
              </Button>
            </form>
          </Form>
        </SheetContent>
      </Sheet>

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-mono">Delete Trade</DialogTitle>
            <DialogDescription>
              Delete {deletingTrade?.tradeType?.toUpperCase()} {formatNumber(deletingTrade?.quantity ?? 0)} {deletingTrade?.symbol} @ {formatCurrency(deletingTrade?.price ?? 0)}? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)} data-testid="button-cancel-delete">Cancel</Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteTrade.isPending}
              data-testid="button-confirm-delete"
            >
              {deleteTrade.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
