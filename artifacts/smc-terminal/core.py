# core.py
import time
import json
import redis
from flask import Blueprint, request, jsonify, Response

# ✅ Verified Constants
from infra.constants import (
    DEFAULT_LOT_NIFTY_OPT, 
    DEFAULT_LOT_SENSEX_OPT,
    TRADE_KEY
)
from services.instrument_lookup import find_option, get_expiries
from services.risk_service import calculate_exit_metrics
from services.trade_store import get_trades as _get_trades, save_trades as _save_trades
from ops.notion_logger import log_trade_to_notion 
from infra import redis_bus as rbus
from ops.system import snapshot

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
core = Blueprint("core", __name__)

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
    nifty_stats  = rbus.get_json("NIFTY_STATS",  None)
    sensex_stats = rbus.get_json("SENSEX_STATS", None)

    # Fall back to raw LTP keys when STATS haven't been written yet
    if not nifty_stats or not nifty_stats.get("lp"):
        raw = rbus.get("ltp:256265")
        nifty_stats = {"lp": float(raw)} if raw else {"lp": 0}

    if not sensex_stats or not sensex_stats.get("lp"):
        raw = rbus.get("ltp:265")
        sensex_stats = {"lp": float(raw)} if raw else {"lp": 0}

    return jsonify({"nifty": nifty_stats, "sensex": sensex_stats})

@core.route("/expiries")
def expiries():
    return jsonify(get_expiries(request.args.get("index")))

@core.route("/system")
def system_health():
    return jsonify(snapshot())


@core.route("/export_data")
def export_data():
    """
    Download a self-contained JSON snapshot for offline testing.
    Contains: today's trades (with full metrics), live Nifty/Sensex stats,
    and today's 1-min + 5-min historical candles for both indices from Kite.
    """
    import os
    from dotenv import load_dotenv
    from kiteconnect import KiteConnect
    from datetime import date

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    today_str = date.today().isoformat()
    payload   = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S IST"),
        "date":        today_str,
        "trades":      _get_trades(),
        "nifty_stats": rbus.get_json("NIFTY_STATS", {}),
        "sensex_stats": rbus.get_json("SENSEX_STATS", {}),
        "candles": {}
    }

    # Fetch today's candles from Kite if session is valid
    try:
        auth = r.hgetall("auth") or {}
        if auth.get("state") == "VALID" and auth.get("token"):
            kite = KiteConnect(api_key=os.getenv("API_KEY"))
            kite.set_access_token(auth["token"])
            for label, token in [("NIFTY", 256265), ("SENSEX", 265)]:
                for interval in ("minute", "5minute"):
                    try:
                        candles = kite.historical_data(
                            token, today_str, today_str, interval, continuous=False
                        )
                        payload["candles"][f"{label}_{interval}"] = [
                            {
                                "ts":    c["date"].strftime("%H:%M") if hasattr(c["date"], "strftime") else str(c["date"]),
                                "open":  c["open"],  "high": c["high"],
                                "low":   c["low"],   "close": c["close"],
                                "volume": c["volume"]
                            }
                            for c in candles
                        ]
                    except Exception as ce:
                        payload["candles"][f"{label}_{interval}"] = {"error": str(ce)}
    except Exception as e:
        payload["candles"]["error"] = str(e)

    filename = f"smc_data_{today_str}.json"
    return Response(
        json.dumps(payload, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

