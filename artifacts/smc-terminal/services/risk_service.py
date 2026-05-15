"""
ROLE: Risk & Cost Calculation Service
"""
from infra.constants import DEFAULT_BROKERAGE, STT_RATE_OPTIONS, GST_RATE

def calculate_exit_metrics(trade: dict, exit_price: float):
    entry_price = float(trade["entryPrice"])
    # ✅ Qty now uses the trade's multiplier (65 or 20)
    qty = int(trade["lots"]) * int(trade["multiplier"])
    
    gross_pnl = (exit_price - entry_price) * qty
    if trade.get("direction") == "SHORT":
        gross_pnl = (entry_price - exit_price) * qty

    # ✅ Cost Logic based on YOUR constants
    # STT on sell side for options
    stt = (exit_price * qty) * STT_RATE_OPTIONS
    # Transaction charges (approx 0.035%)
    txn_charges = (entry_price + exit_price) * qty * 0.00035
    # GST on Brokerage + Txn
    gst = (DEFAULT_BROKERAGE + txn_charges) * GST_RATE
    
    total_charges = DEFAULT_BROKERAGE + stt + txn_charges + gst
    net_pnl = round(gross_pnl - total_charges, 2)

    return {
        "net_pnl": net_pnl,
        "brokerage": round(total_charges, 2)
    }
def calculate_live_pnl(entry, ltp, qty, direction):
    if direction == "LONG":
        return round((ltp - entry) * qty, 2)
    return round((entry - ltp) * qty, 2)
