# core.py
import time
import json
import redis
from flask import Blueprint, request, jsonify

# ✅ Verified Constants
from infra.constants import (
    DEFAULT_LOT_NIFTY_OPT, 
    DEFAULT_LOT_SENSEX_OPT,
    TRADE_KEY
)
from services.instrument_lookup import find_option, get_expiries
from services.risk_service import calculate_exit_metrics
from ops.notion_logger import log_trade_to_notion 
from infra import redis_bus as rbus
from ops.system import snapshot

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
core = Blueprint("core", __name__)

def _get_trades():
    raw = r.get(TRADE_KEY)
    return json.loads(raw) if raw else []

def _save_trades(trades):
    r.set(TRADE_KEY, json.dumps(trades))

@core.route("/nifty_card")
def nifty_card():
    stats = rbus.get_json("NIFTY_STATS", {"lp": 0, "change": 0, "p_change": 0, "ts": "--"})
    stats["market"] = snapshot()["market"]
    return jsonify(stats)

@core.route("/trade_state")
def trade_state():
    """Handles LTP, MFE/MAE points, filtering (date), and sorting."""

    trades = _get_trades()

    # ✅ FILTER: Only active + today's trades
    today = time.strftime("%Y-%m-%d")
    trades = [
        t for t in trades
        if t["status"] == "ACTIVE" or t.get("date") == today
    ]

    updated = False

    for t in trades:
        ltp_val = r.get(f"ltp:{t['token']}")
        if ltp_val:
            ltp = float(ltp_val)
            t["ltp"] = ltp

            entry = float(t["entryPrice"])
            qty = int(t["lots"]) * int(t.get("multiplier", 1))

            if t["status"] == "ACTIVE":
                t["net_pnl"] = round(
                    (ltp - entry) * qty if t["direction"] == "LONG"
                    else (entry - ltp) * qty,
                    2
                )

            # ✅ Update MFE / MAE
            t["mfe"] = round(
                max(
                    float(t.get("mfe", 0)),
                    max(
                        0,
                        ltp - entry if t["direction"] == "LONG"
                        else entry - ltp
                    )
                ),
                2
            )

            t["mae"] = round(
                min(
                    float(t.get("mae", 0)),
                    min(
                        0,
                        ltp - entry if t["direction"] == "LONG"
                        else entry - ltp
                    )
                ),
                2
            )

            updated = True

    # ✅ Sort: ACTIVE first, then newest
    trades.sort(key=lambda x: (x["status"] != "ACTIVE", -x.get("created_at", 0)))

    if updated:
        _save_trades(trades)

    return jsonify(trades)



@core.route("/trade", methods=["POST"])
def create_trade():
    data = request.json
    instr = find_option(data["index"], data["strike"], data["option_type"], data.get("expiry"))
    if not instr: return jsonify({"error": "Instrument not found"}), 400

    mult = DEFAULT_LOT_NIFTY_OPT if data["index"] == "NIFTY" else DEFAULT_LOT_SENSEX_OPT
    
    # ✅ ADDED: Capture SL and TG from incoming request
    new_trade = {
        "id": f"T{int(time.time()*1000)}", 
        "symbol": instr["symbol"], 
        "token": instr["token"],
        "index": data["index"],
        "entryPrice": float(data["entryPrice"]), 
        "lots": int(data["lots"]), 
        "sl": float(data.get("sl", 0)),  # <-- NEW
        "tg": float(data.get("tg", 0)),  # <-- NEW
        "multiplier": mult,
        "direction": data.get("direction", "LONG"), 
        "status": "ACTIVE", 
        "created_at": time.time(), 
        "setup": data.get("setup", "SMC"), 
        "entry_emotion": data.get("entry_emotion", "Calm"), 
        "net_pnl": 0, "mfe": 0, "mae": 0, "ltp": 0,
        "entry_time": data.get("entry_time", time.strftime("%H:%M:%S")),
        "date": time.strftime("%Y-%m-%d")
    }
    
    trades = _get_trades()
    trades.append(new_trade)
    _save_trades(trades)
    return jsonify(new_trade)

@core.route("/trade/exit", methods=["POST"])
def exit_trade():
    data = request.json
    trades = _get_trades()
    updated = False
    for t in trades:
        if t["id"] == data["id"] and t["status"] == "ACTIVE":
            metrics = calculate_exit_metrics(t, float(data["exit_price"]))
            t.update({
                "status": "CLOSED", 
                "exit_price": float(data["exit_price"]), 
                "exit_time": data.get("exit_time", time.strftime("%H:%M:%S")),
                "exit_emotion": data.get("exit_emotion", "Disciplined"), 
                "net_pnl": metrics["net_pnl"],
                "brokerage": metrics["brokerage"]
            })
            
            # ✅ PASS DATA TO NOTION
            log_trade_to_notion(t) 
            updated = True; break
            
    if updated: _save_trades(trades)
    return jsonify({"status": "ok"})

@core.route("/last_tick")
def last_tick():
    return jsonify({"nifty": rbus.get_json("NIFTY_STATS", {"lp": 0}), "sensex": rbus.get_json("SENSEX_STATS", {"lp": 0})})

@core.route("/expiries")
def expiries():
    return jsonify(get_expiries(request.args.get("index")))

