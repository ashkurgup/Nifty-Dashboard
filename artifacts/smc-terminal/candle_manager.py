import redis
import json
from datetime import datetime

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# SMC Structural Levels
PWH = 24601.70
PWL = 23555.60
STRUCTURAL_4H = [24482.0, 24400.0, 23800.0]

def update_nifty_stats(ltp):
    try:
        stats_raw = r.get("NIFTY_STATS")
        stats = json.loads(stats_raw) if stats_raw else {}
        
        # PDC fetched fresh from Kite on WS connect and stored in Redis
        pdc_raw = r.get("NIFTY_PDC")
        prev_close = float(pdc_raw) if pdc_raw else stats.get("close", 0)
        
        high = max(stats.get("high", ltp), ltp)
        low = min(stats.get("low", ltp), ltp)
        
        change = ltp - prev_close
        p_change = (change / prev_close) * 100 if prev_close != 0 else 0
        
        resistances = sorted([p for p in STRUCTURAL_4H if p > ltp])
        near_r = resistances[0] if resistances else PWH
        near_s = PWL

        nifty_card = {
            "lp": round(ltp, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": prev_close,
            "change": round(change, 2),
            "p_change": round(p_change, 2),
            "ts": datetime.now().strftime("%d/%m %H:%M:%S"),
            "sr_r_val": near_r,
            "sr_r_desc": "4H Structure",
            "sr_s_val": near_s,
            "sr_s_desc": "PWL Support",
            "fvg_1_val": "None",
            "fvg_1_desc": "Near",
            "fvg_2_val": "None",
            "fvg_2_desc": "Next"
        }
        
        r.set("NIFTY_STATS", json.dumps(nifty_card))
        r.set("NIFTY", json.dumps({"lp": ltp}))
        
        return nifty_card
    except Exception as e:
        print(f"[CANDLE MGR ERR] {e}")


def update_sensex_stats(ltp):
    try:
        stats_raw = r.get("SENSEX_STATS")
        stats = json.loads(stats_raw) if stats_raw else {}

        pdc_raw = r.get("SENSEX_PDC")
        prev_close = float(pdc_raw) if pdc_raw else stats.get("close", 0)

        high = max(stats.get("high", ltp), ltp)
        low  = min(stats.get("low",  ltp), ltp)

        change   = ltp - prev_close
        p_change = (change / prev_close) * 100 if prev_close != 0 else 0

        sensex_card = {
            "lp":       round(ltp, 2),
            "high":     round(high, 2),
            "low":      round(low, 2),
            "close":    prev_close,
            "change":   round(change, 2),
            "p_change": round(p_change, 2),
            "ts":       datetime.now().strftime("%H:%M:%S"),
        }

        r.set("SENSEX_STATS", json.dumps(sensex_card))
        return sensex_card
    except Exception as e:
        print(f"[CANDLE MGR SENSEX ERR] {e}")
