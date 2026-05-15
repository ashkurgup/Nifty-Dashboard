# services/market_service.py
import json
import redis
from infra.constants import REDIS_TRADES
from services.risk_service import calculate_live_pnl

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

def update_excursion(token: str, ltp: float):
    try:
        raw = r.get(REDIS_TRADES) or "[]"
        trades = json.loads(raw)
        updated = False

        for t in trades:
            if t.get("status") == "ACTIVE" and str(t.get("token")) == str(token):
                entry = float(t["entryPrice"])
                qty = int(t["lots"]) * int(t.get("multiplier", 1))
                direction = t.get("direction", "LONG")

                # Update LTP
                t["ltp"] = ltp
                
                # Centralized Math
                t["net_pnl"] = calculate_live_pnl(entry, ltp, qty, direction)

                # MFE/MAE Logic
                diff = ltp - entry if direction == "LONG" else entry - ltp
                t["mfe"] = round(max(float(t.get("mfe", 0)), diff), 2)
                
                # Drawdown tracking
                if diff < 0:
                    t["mae"] = round(max(float(t.get("mae", 0)), abs(diff)), 2)

                updated = True

        if updated:
            r.set(REDIS_TRADES, json.dumps(trades))

    except Exception as e:
        print(f"[MARKET SERVICE ERROR] {e}")
