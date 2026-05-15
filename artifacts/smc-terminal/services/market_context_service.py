"""
Market Context Service — Gap, PDH/PDL, ORH/ORL for Nifty.

All price data uses Nifty 50 index (token 256265) — same as PDC in Redis.

Gap logic:
  Gap exists when today's 09:15 open differs from PDC by >= 15 pts.
  Bullish gap  = open > PDC  (gapped up)
  Bearish gap  = open < PDC  (gapped down)
  Gap closed   = any 5-min candle's range touched PDC

Opening Range:
  Single 15-min candle (09:15–09:30)
  ORH = high, ORL = low of that candle

Candle patterns: Mar / Ham / Inv / Doji / Spin T / Oth
  S-variants (S Mar / S Ham / S Inv / S Doji) require total range >= 50 pts
  and the closing-side wick <= 3 pts.

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


def _candle_pattern(o, h, l, c) -> str:
    """Classify a candle into a short label using S-patterns first."""
    total = h - l
    if total == 0:
        return "Doji"

    body       = abs(c - o)
    body_top   = max(o, c)
    body_bot   = min(o, c)
    upper_wick = h - body_top
    lower_wick = body_bot - l
    is_bull    = c >= o

    body_pct  = body  / total * 100
    upper_pct = upper_wick / total * 100
    lower_pct = lower_wick / total * 100

    close_wick = upper_wick if is_bull else lower_wick

    # ── S patterns (range >= 50 pts, closing-side wick <= 3 pts) ──────────
    if total >= 50 and close_wick <= 3:
        other_pct = lower_pct if is_bull else upper_pct

        # S Mar: body >= 85%, other wick <= 10%
        if body_pct >= 85 and other_pct <= 10:
            return "S Mar"

        # S Ham: long lower wick (bull close near top → upper wick = close wick)
        if lower_pct >= 50 and upper_pct <= 20:
            return "S Ham"

        # S Inv: long upper wick (bear close near bottom → lower wick = close wick)
        if upper_pct >= 50 and lower_pct <= 20:
            return "S Inv"

        # S Doji: one wick >= 50%, other <= 20%
        if (lower_pct >= 50 and upper_pct <= 20) or (upper_pct >= 50 and lower_pct <= 20):
            return "S Doji"

    # ── Standard patterns ─────────────────────────────────────────────────
    if body_pct >= 80 and upper_pct <= 10 and lower_pct <= 10:
        return "Mar"

    if lower_pct >= 55 and upper_pct <= 15 and body_pct <= 30:
        return "Ham"

    if upper_pct >= 55 and lower_pct <= 15 and body_pct <= 30:
        return "Inv"

    if body_pct <= 10:
        return "Doji"

    if 10 <= body_pct <= 35 and upper_pct >= 25 and lower_pct >= 25:
        return "Spin T"

    return "Oth"


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
        "gap_val": None,
        "pdh": None, "pdl": None, "pdo": None, "pdc": None, "pd_pattern": None,
        "orh": None, "orl": None, "or_pattern": None,
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

    # ── 2. Prev day OHLC — last completed trading day ────────────────────
    try:
        from_dt     = (date.today() - timedelta(days=7)).isoformat()
        prev_to     = (date.today() - timedelta(days=1)).isoformat()
        day_candles = kite.historical_data(_IDX, from_dt, prev_to, "day", continuous=False)
        prev_day    = day_candles[-1] if day_candles else None
        pdh        = _fmt(prev_day["high"])  if prev_day else None
        pdl        = _fmt(prev_day["low"])   if prev_day else None
        pdo        = _fmt(prev_day["open"])  if prev_day else None
        pdc_day    = _fmt(prev_day["close"]) if prev_day else None
        pd_pattern = _candle_pattern(
            prev_day["open"], prev_day["high"], prev_day["low"], prev_day["close"]
        ) if prev_day else None
        pd_bull = bool(prev_day["close"] >= prev_day["open"]) if prev_day else None
    except Exception as e:
        print(f"[MktCtx] PDH/PDL fetch failed: {e}")
        pdh = pdl = pdo = pdc_day = pd_pattern = pd_bull = None

    # ── 3. Gap analysis ───────────────────────────────────────────────────
    pdc_raw = _r.get("NIFTY_PDC")
    pdc     = float(pdc_raw) if pdc_raw else None

    gap = gap_dir = gap_closed = gap_close_time = None

    if pdc and candles:
        today_open = candles[0]["open"]
        gap_pct    = (today_open - pdc) / pdc * 100

        gap_pts = round(today_open - pdc, 2)

        if abs(gap_pts) < 15:
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

    # ── 4. Opening Range (single 15-min candle 09:15–09:30) ──────────────
    try:
        candles_15 = kite.historical_data(_IDX, today, today, "15minute", continuous=False)
        first_15   = candles_15[0] if candles_15 else None
        if first_15:
            orh        = _fmt(first_15["high"])
            orl        = _fmt(first_15["low"])
            or_pattern = _candle_pattern(
                first_15["open"], first_15["high"], first_15["low"], first_15["close"]
            )
            or_bull = bool(first_15["close"] >= first_15["open"])
        else:
            orh = orl = or_pattern = or_bull = None
    except Exception as e:
        print(f"[MktCtx] OR fetch failed: {e}")
        orh = orl = or_pattern = or_bull = None

    result = {
        "gap":            gap,
        "gap_dir":        gap_dir,
        "gap_val":        gap_pts if gap == "Yes" else None,
        "gap_closed":     gap_closed,
        "gap_close_time": gap_close_time,
        "pdh":            pdh,
        "pdl":            pdl,
        "pdo":            pdo,
        "pdc":            pdc_day,
        "pd_pattern":     pd_pattern,
        "pd_bull":        pd_bull,
        "pd_range":       round(pdh - pdl) if pdh and pdl else None,
        "orh":            orh,
        "orl":            orl,
        "or_pattern":     or_pattern,
        "or_bull":        or_bull,
        "or_range":       round(orh - orl) if orh and orl else None,
        "ts":             datetime.now(_IST).strftime("%H:%M"),
    }
    _r.setex(_KEY, _TTL, json.dumps(result))
    return result
