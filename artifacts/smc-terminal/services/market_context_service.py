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
import os, json, redis, pytz, pathlib
from datetime import datetime, date, timedelta

_r    = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST  = pytz.timezone("Asia/Kolkata")
_KEY  = "mkt_ctx"
_TTL  = 300   # 5 min short cache
_IDX  = 256265

_PD_FIELDS = ["pdh","pdl","pdo","pdc","pd_pattern","pd_bull","pd_body","pd_bd"]
_OR_FIELDS = ["orh","orl","or_pattern","or_bull","or_body","or_bd"]

# File-based LKG — survives Redis restart (which uses shutdown nosave)
_LKG_FILE = pathlib.Path(__file__).parent.parent / "data" / "mkt_ctx_lkg.json"
_LKG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_lkg() -> dict:
    try:
        if _LKG_FILE.exists():
            return json.loads(_LKG_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_lkg(data: dict):
    try:
        _LKG_FILE.write_text(json.dumps(data))
    except Exception:
        pass


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


# ── Weekly candle cache ────────────────────────────────────────────────────
_WEEKLY_KEY = "WEEKLY_LEVELS"
_WEEKLY_TTL = 3600


def _weekly_candle_pattern(o, h, l, c):
    """Simplified candle pattern (no S-variants) for weekly bars."""
    total = h - l
    if total == 0:
        return "Doji", c > o, 0.0, 0
    body      = abs(c - o)
    upper     = h - max(o, c)
    lower     = min(o, c) - l
    body_pct  = body  / total * 100
    upper_pct = upper / total * 100
    lower_pct = lower / total * 100

    if body_pct >= 80 and upper_pct <= 10 and lower_pct <= 10:
        pat = "Mar"
    elif lower_pct >= 55 and upper_pct <= 15 and body_pct <= 30:
        pat = "Ham"
    elif upper_pct >= 55 and lower_pct <= 15 and body_pct <= 30:
        pat = "Inv"
    elif body_pct <= 10:
        pat = "Doji"
    elif body_pct <= 35 and upper_pct >= 25 and lower_pct >= 25:
        pat = "SpinT"
    else:
        pat = "Oth"

    return pat, c > o, round(body, 1), int(body_pct)


def _get_weekly_levels(kite) -> dict:
    """Fetch prev-week and curr-week OHLC for Nifty. Own 1h cache."""
    empty = {k: None for k in [
        "pw_high", "pw_low", "pw_open", "pw_close",
        "pw_pattern", "pw_bull", "pw_body", "pw_bd",
        "cw_high", "cw_low", "cw_open", "cw_close",
        "cw_pattern", "cw_bull", "cw_body", "cw_bd",
    ]}

    cached_raw = _r.get(_WEEKLY_KEY)
    if cached_raw:
        try:
            return json.loads(cached_raw)
        except Exception:
            pass

    if kite is None:
        return empty

    try:
        from_dt = (date.today() - timedelta(days=21)).isoformat()
        to_dt   = date.today().isoformat()
        bars    = kite.historical_data(_IDX, from_dt, to_dt, "day", continuous=False)
    except Exception as e:
        print(f"[Weekly] fetch failed: {e}")
        return empty

    if not bars:
        return empty

    try:
        today_iso              = date.today().isocalendar()
        curr_year, curr_week   = today_iso[0], today_iso[1]

        if curr_week == 1:
            prev_year_num  = curr_year - 1
            prev_week_num  = date(prev_year_num, 12, 28).isocalendar()[1]
        else:
            prev_year_num  = curr_year
            prev_week_num  = curr_week - 1

        prev_bars, curr_bars = [], []
        for b in bars:
            dt  = b["date"]
            d   = dt.date() if hasattr(dt, "date") else dt
            iso = d.isocalendar()
            by, bw = iso[0], iso[1]
            if by == curr_year and bw == curr_week:
                curr_bars.append(b)
            elif by == prev_year_num and bw == prev_week_num:
                prev_bars.append(b)

        result = dict(empty)

        if prev_bars:
            pw_o = _fmt(prev_bars[0]["open"])
            pw_h = _fmt(max(b["high"]  for b in prev_bars))
            pw_l = _fmt(min(b["low"]   for b in prev_bars))
            pw_c = _fmt(prev_bars[-1]["close"])
            pat, bull, body, bd = _weekly_candle_pattern(pw_o, pw_h, pw_l, pw_c)
            result.update({
                "pw_open": pw_o, "pw_high": pw_h,
                "pw_low":  pw_l, "pw_close": pw_c,
                "pw_pattern": pat, "pw_bull": bull,
                "pw_body": body,  "pw_bd": bd,
            })

        if curr_bars:
            cw_o = _fmt(curr_bars[0]["open"])
            cw_h = _fmt(max(b["high"]  for b in curr_bars))
            cw_l = _fmt(min(b["low"]   for b in curr_bars))
            cw_c = _fmt(curr_bars[-1]["close"])
            pat, bull, body, bd = _weekly_candle_pattern(cw_o, cw_h, cw_l, cw_c)
            result.update({
                "cw_open": cw_o, "cw_high": cw_h,
                "cw_low":  cw_l, "cw_close": cw_c,
                "cw_pattern": pat, "cw_bull": bull,
                "cw_body": body,  "cw_bd": bd,
            })

        _r.setex(_WEEKLY_KEY, _WEEKLY_TTL, json.dumps(result))
        return result

    except Exception as e:
        print(f"[Weekly] compute failed: {e}")
        return empty


def get_market_context() -> dict:
    cached = _r.get(_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    kite = _kite()

    def _with_lkg(base: dict) -> dict:
        """Merge last-known-good values into base for any None PD/OR fields."""
        lkg = _load_lkg()
        if not lkg:
            return base
        if base.get("pdh") is None:
            for f in _PD_FIELDS:
                base[f] = lkg.get(f)
        if base.get("orh") is None:
            for f in _OR_FIELDS:
                base[f] = lkg.get(f)
        return base

    empty = {
        "gap": None, "gap_dir": None, "gap_closed": None, "gap_close_time": None,
        "gap_val": None,
        "pdh": None, "pdl": None, "pdo": None, "pdc": None, "pd_pattern": None,
        "orh": None, "orl": None, "or_pattern": None,
        "ts": datetime.now(_IST).strftime("%H:%M"),
    }

    if kite is None:
        base = _with_lkg(empty)
        base.update(_get_weekly_levels(None))
        return base

    today = date.today().isoformat()

    # ── 1. Today's 5-min candles (index) ─────────────────────────────────
    try:
        candles = kite.historical_data(_IDX, today, today, "5minute", continuous=False)
    except Exception as e:
        print(f"[MktCtx] candle fetch failed: {e}")
        base = _with_lkg(empty)
        base.update(_get_weekly_levels(kite))
        return base

    if not candles:
        base = _with_lkg(empty)
        base.update(_get_weekly_levels(kite))
        return base

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
        pd_bull  = bool(prev_day["close"] >= prev_day["open"]) if prev_day else None
        pd_body  = round(abs(prev_day["close"] - prev_day["open"])) if prev_day else None
        pd_range_val = (pdh - pdl) if pdh and pdl else None
        pd_bd    = round(pd_body / pd_range_val * 100) if pd_body and pd_range_val else None
    except Exception as e:
        print(f"[MktCtx] PDH/PDL fetch failed: {e}")
        pdh = pdl = pdo = pdc_day = pd_pattern = pd_bull = pd_body = pd_bd = None

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
            or_bull      = bool(first_15["close"] >= first_15["open"])
            or_body      = round(abs(first_15["close"] - first_15["open"]))
            or_range_val = orh - orl if orh and orl else None
            or_bd        = round(or_body / or_range_val * 100) if or_body and or_range_val else None
        else:
            orh = orl = or_pattern = or_bull = or_body = or_bd = None
    except Exception as e:
        print(f"[MktCtx] OR fetch failed: {e}")
        orh = orl = or_pattern = or_bull = or_body = or_bd = None

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
        "pd_body":        pd_body,
        "pd_bd":          pd_bd,
        "orh":            orh,
        "orl":            orl,
        "or_pattern":     or_pattern,
        "or_bull":        or_bull,
        "or_body":        or_body,
        "or_bd":          or_bd,
        "ts":             datetime.now(_IST).strftime("%H:%M"),
    }

    # Apply last-known-good for any fields still None after fresh fetch
    result = _with_lkg(result)

    # Update file-based LKG whenever we have valid data (survives Redis restarts)
    if result.get("pdh") or result.get("orh"):
        _save_lkg(result)

    # ── Weekly candle data (own 1h cache) ─────────────────────────────────
    result.update(_get_weekly_levels(kite))

    _r.setex(_KEY, _TTL, json.dumps(result))
    return result
