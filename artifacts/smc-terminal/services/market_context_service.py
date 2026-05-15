"""
Market Context Service — Gap, PDH/PDL, ORH/ORL for Nifty.

All price data uses Nifty 50 index (token 256265) — same as PDC in Redis.

Gap logic:
  Gap exists when today's 09:15 open differs from PDC by >= 0.05%.
  Bullish gap  = open > PDC  (gapped up)
  Bearish gap  = open < PDC  (gapped down)
  Gap closed   = any 5-min candle's range touched PDC (low<=PDC for bull, high>=PDC for bear)

Opening Range:
  09:15 + 09:20 + 09:25 candles combined  (full 15 minutes)
  ORH = max of all three highs
  ORL = min of all three lows

Cache: Redis key `mkt_ctx`, TTL 5 min.
"""
import os, json, redis, pytz
from datetime import datetime, date, timedelta

_r   = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST = pytz.timezone("Asia/Kolkata")
_KEY = "mkt_ctx"
_TTL = 300   # 5 min
_IDX = 256265


def _kite():
    auth = _r.hgetall("auth") or {}
    if auth.get("state") != "VALID" or not auth.get("token"):
        return None
    from kiteconnect import KiteConnect
    k = KiteConnect(api_key=os.getenv("API_KEY"))
    k.set_access_token(auth["token"])
    return k


def _fmt(v):
    """Round to 2 dp."""
    return round(float(v), 2) if v is not None else None


def get_market_context() -> dict:
    cached = _r.get(_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    kite = _kite()
    empty = {
        "gap": None, "gap_dir": None, "gap_closed": None, "gap_close_time": None,
        "pdh": None, "pdl": None,
        "orh": None, "orl": None,
        "ts": datetime.now(_IST).strftime("%H:%M"),
    }

    if kite is None:
        return empty

    today = date.today().isoformat()

    # ── 1. Today's 5-min candles (index) ─────────────────────────────────
    try:
        candles = kite.historical_data(_IDX, today, today, "5minute", continuous=False)
    except Exception as e:
        print(f"[MktCtx] candle fetch failed: {e}")
        return empty

    if not candles:
        return empty

    # ── 2. PDH / PDL — last completed trading day ────────────────────────
    try:
        from_dt = (date.today() - timedelta(days=7)).isoformat()
        prev_to  = (date.today() - timedelta(days=1)).isoformat()
        day_candles = kite.historical_data(_IDX, from_dt, prev_to, "day", continuous=False)
        prev_day = day_candles[-1] if day_candles else None
        pdh = _fmt(prev_day["high"]) if prev_day else None
        pdl = _fmt(prev_day["low"])  if prev_day else None
    except Exception as e:
        print(f"[MktCtx] PDH/PDL fetch failed: {e}")
        pdh = pdl = None

    # ── 3. Gap analysis ───────────────────────────────────────────────────
    pdc_raw = _r.get("NIFTY_PDC")
    pdc     = float(pdc_raw) if pdc_raw else None

    gap = gap_dir = gap_closed = gap_close_time = None

    if pdc and candles:
        today_open = candles[0]["open"]
        gap_pct    = (today_open - pdc) / pdc * 100

        if abs(gap_pct) < 0.05:
            gap = "No"
        else:
            gap     = "Yes"
            gap_dir = "Bullish" if today_open > pdc else "Bearish"

            # Scan candles to find when gap was closed
            gap_closed = False
            for c in candles:
                t = c["date"]
                hhmm = t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)[11:16]
                if gap_dir == "Bullish" and c["low"] <= pdc:
                    gap_closed     = True
                    gap_close_time = hhmm
                    break
                elif gap_dir == "Bearish" and c["high"] >= pdc:
                    gap_closed     = True
                    gap_close_time = hhmm
                    break

    # ── 4. Opening Range (09:15 + 09:20 + 09:25) ─────────────────────────
    or_candles = [
        c for c in candles
        if hasattr(c["date"], "hour")
        and c["date"].hour == 9
        and c["date"].minute in (15, 20, 25)
    ]
    if len(or_candles) >= 1:
        orh = _fmt(max(c["high"] for c in or_candles))
        orl = _fmt(min(c["low"]  for c in or_candles))
    else:
        orh = orl = None

    result = {
        "gap":            gap,
        "gap_dir":        gap_dir,
        "gap_closed":     gap_closed,
        "gap_close_time": gap_close_time,
        "pdh":            pdh,
        "pdl":            pdl,
        "orh":            orh,
        "orl":            orl,
        "ts":             datetime.now(_IST).strftime("%H:%M"),
    }
    _r.setex(_KEY, _TTL, json.dumps(result))
    return result
