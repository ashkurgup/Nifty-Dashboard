"""
Nifty 5-min volume service.

Fetches the last 6 completed 5-minute candles for Nifty 50 (index token 256265)
from Kite's historical API.  Caches in Redis for 4 minutes so the box refreshes
just before each new candle completes.

Returns a dict:
  {
    "candles": [{"time": "09:15", "vol": 123456}, ...],   # oldest → newest
    "avg":     98765,
    "ts":      "14:30"   # IST time of last fetch
  }
Returns None when Kite session is unavailable or market is closed.
"""
import os
import json
import redis
import pytz
from datetime import datetime, date

_r       = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST     = pytz.timezone("Asia/Kolkata")
_TOKEN   = 256265          # Nifty 50 index
_CACHE   = "nifty_vol_5m"
_TTL     = 240             # 4 minutes
_N       = 6               # number of candles to show


def _kite():
    auth = _r.hgetall("auth") or {}
    if auth.get("state") != "VALID" or not auth.get("token"):
        return None
    from kiteconnect import KiteConnect
    k = KiteConnect(api_key=os.getenv("API_KEY"))
    k.set_access_token(auth["token"])
    return k


def get_nifty_volume() -> dict | None:
    """Return last 6 5-min candle volumes for Nifty, with average."""
    cached = _r.get(_CACHE)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    kite = _kite()
    if kite is None:
        return None

    try:
        today = date.today().isoformat()
        candles = kite.historical_data(
            _TOKEN, today, today, "5minute", continuous=False
        )
    except Exception as e:
        print(f"[Volume] Kite fetch failed: {e}")
        return None

    if not candles:
        return None

    # Take last _N completed candles (Kite returns only completed ones)
    recent = candles[-_N:]
    items  = []
    for c in recent:
        ts = c["date"]
        if hasattr(ts, "strftime"):
            t = ts.strftime("%H:%M")
        else:
            t = str(ts)[11:16]
        items.append({"time": t, "vol": int(c.get("volume", 0))})

    vols = [i["vol"] for i in items]
    avg  = int(sum(vols) / len(vols)) if vols else 0

    result = {
        "candles": items,
        "avg":     avg,
        "ts":      datetime.now(_IST).strftime("%H:%M"),
    }
    _r.setex(_CACHE, _TTL, json.dumps(result))
    return result
