"""
Nifty 5-min volume service — uses near-month Nifty Futures (NFO).

Index token 256265 always returns volume=0 from Kite.
Futures have real traded volume (contracts per candle).

Caches:
  nifty_vol_token  — near-month futures token, TTL 6h (rolls automatically)
  nifty_vol_5m     — last 6 candle volumes, TTL 4 min

Returns:
  {
    "candles":  [{"time": "09:15", "vol": 75140}, ...],  # oldest → newest
    "avg":       98765,
    "symbol":   "NIFTY26MAYFUT",
    "ts":        "14:30"
  }
  or None when Kite session is unavailable / market closed.
"""
import os
import json
import redis
import pytz
from datetime import datetime, date

_r        = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST      = pytz.timezone("Asia/Kolkata")
_N        = 6
_VOL_KEY  = "nifty_vol_5m"
_TOK_KEY  = "nifty_vol_token"
_VOL_TTL  = 240    # 4 min — refresh just before each new candle
_TOK_TTL  = 21600  # 6 h — token only changes on expiry day


def _kite():
    auth = _r.hgetall("auth") or {}
    if auth.get("state") != "VALID" or not auth.get("token"):
        return None
    from kiteconnect import KiteConnect
    k = KiteConnect(api_key=os.getenv("API_KEY"))
    k.set_access_token(auth["token"])
    return k


def _near_month_token(kite) -> tuple[int, str] | tuple[None, None]:
    """Return (instrument_token, tradingsymbol) for the nearest Nifty futures expiry."""
    cached = _r.get(_TOK_KEY)
    if cached:
        try:
            d = json.loads(cached)
            return d["token"], d["symbol"]
        except Exception:
            pass

    try:
        instruments = kite.instruments("NFO")
        futs = [
            i for i in instruments
            if i["name"] == "NIFTY" and i["instrument_type"] == "FUT"
        ]
        futs.sort(key=lambda x: x["expiry"])
        near = futs[0]
        token  = near["instrument_token"]
        symbol = near["tradingsymbol"]
        _r.setex(_TOK_KEY, _TOK_TTL, json.dumps({"token": token, "symbol": symbol}))
        return token, symbol
    except Exception as e:
        print(f"[Volume] instrument lookup failed: {e}")
        return None, None


def get_nifty_volume() -> dict | None:
    """Return last 6 completed 5-min candle volumes for Nifty Futures."""
    cached = _r.get(_VOL_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    kite = _kite()
    if kite is None:
        return None

    token, symbol = _near_month_token(kite)
    if token is None:
        return None

    try:
        today   = date.today().isoformat()
        candles = kite.historical_data(token, today, today, "5minute", continuous=False)
    except Exception as e:
        print(f"[Volume] historical_data failed: {e}")
        return None

    if not candles:
        return None

    recent = candles[-_N:]
    items  = []
    for c in recent:
        ts = c["date"]
        t  = ts.strftime("%H:%M") if hasattr(ts, "strftime") else str(ts)[11:16]
        items.append({"time": t, "vol": int(c.get("volume", 0))})

    vols = [i["vol"] for i in items]
    avg  = int(sum(vols) / len(vols)) if vols else 0

    result = {
        "candles": items,
        "avg":     avg,
        "symbol":  symbol,
        "ts":      datetime.now(_IST).strftime("%H:%M"),
    }
    _r.setex(_VOL_KEY, _VOL_TTL, json.dumps(result))
    return result
