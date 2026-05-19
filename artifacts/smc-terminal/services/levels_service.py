"""
SR Levels and FVG detection for Nifty 50.

SR Levels (Swing-based):
  Detects swing highs/lows using N-bar method.
  1H: N=5 bars each side, last 30 trading days.
  4H: N=3 bars each side (daily bars proxy), last 30 trading days.
  Strength scored by move after formation vs ATR.
  Dedup: 4H wins within 30pts of 1H level.
  Excludes levels within 1x ATR_5min of LTP (too close to act on).
  Shows nearest 2 above + 2 below LTP.
  Cache: SR_LEVELS_CACHE, 300s.

FVG Levels:
  Detects bullish/bearish Fair Value Gaps in 5m bars, last 3 trading days.
  Excludes first 3 and last 5 bars of each session.
  IFVG when c2 body >= 0.3 * ATR_5m.
  Non-mitigated only. Within 400 pts of LTP. Max 4, sorted by distance.
  Cache: FVG_CACHE, 300s.

NOTE: side / distance always recalculated at call time using live LTP.
"""
import os
import json
import redis
import pytz
from datetime import datetime, date, timedelta

_r   = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST = pytz.timezone("Asia/Kolkata")
_IDX = 256265

_SR_KEY    = "SR_LEVELS_CACHE"
_SR_4H_KEY = "SR_4H_CACHE"
_FVG_KEY   = "FVG_CACHE"
_TTL       = 300
_TTL_4H    = 600


# ── helpers ────────────────────────────────────────────────────────────────

def _kite():
    auth = _r.hgetall("auth") or {}
    if auth.get("state") != "VALID" or not auth.get("token"):
        return None
    from kiteconnect import KiteConnect
    k = KiteConnect(api_key=os.getenv("API_KEY"))
    k.set_access_token(auth["token"])
    return k


def _cached(key, ttl=_TTL):
    raw = _r.get(key)
    if not raw:
        return None
    try:
        d = json.loads(raw)
        if (datetime.now().timestamp() - d.get("_ts", 0)) < ttl:
            return d.get("data")
    except Exception:
        pass
    return None


def _save(key, data, ttl=_TTL):
    payload = json.dumps({"_ts": datetime.now().timestamp(), "data": data})
    _r.setex(key, ttl + 60, payload)


def _last_cached(key):
    raw = _r.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw).get("data")
    except Exception:
        return None


def _recalc(levels: list, ltp: float) -> list:
    """Recalculate side and distance for every level using current LTP."""
    out = []
    for lvl in levels:
        lvl = dict(lvl)
        lvl["side"]     = "above" if lvl["price"] > ltp else "below"
        lvl["distance"] = round(abs(lvl["price"] - ltp), 2)
        out.append(lvl)
    return out


def _get_atr_5m():
    """Get ATR 5min from Redis or return default."""
    try:
        raw = _r.get("NIFTY_ATR_5M")
        if raw:
            return float(raw)
    except Exception:
        pass
    return 43.0  # default fallback


# ── swing detection helpers ────────────────────────────────────────────────

def _find_swing_highs_lows(bars, n, atr, tf_label):
    """
    Find swing highs and lows using N-bar method.
    A swing high: bar[i].high is highest in bars[i-n:i+n+1]
    A swing low:  bar[i].low  is lowest  in bars[i-n:i+n+1]
    Strength scored by move after formation vs ATR.
    """
    swings = []
    for i in range(n, len(bars) - n):
        window = bars[i - n: i + n + 1]
        bar    = bars[i]

        # Swing high
        if bar["high"] == max(b["high"] for b in window):
            # Move after: bar[i].high - min low in next n bars
            next_bars  = bars[i + 1: i + n + 1]
            move_after = bar["high"] - min(b["low"] for b in next_bars) if next_bars else 0
            strength   = min(4, max(1, int(move_after / (0.5 * atr)) + 1))
            swings.append({
                "price":    round(bar["high"], 2),
                "type":     "Resistance",
                "tf":       tf_label,
                "strength": strength,
                "move":     round(move_after, 1),
                "side":     "",
                "distance": 0,
            })

        # Swing low
        if bar["low"] == min(b["low"] for b in window):
            next_bars  = bars[i + 1: i + n + 1]
            move_after = max(b["high"] for b in next_bars) - bar["low"] if next_bars else 0
            strength   = min(4, max(1, int(move_after / (0.5 * atr)) + 1))
            swings.append({
                "price":    round(bar["low"], 2),
                "type":     "Support",
                "tf":       tf_label,
                "strength": strength,
                "move":     round(move_after, 1),
                "side":     "",
                "distance": 0,
            })

    return swings


def _deduplicate_swings(swings, tolerance=30):
    """
    Remove near-duplicate levels.
    4H wins over 1H when within tolerance pts.
    Higher strength wins otherwise.
    """
    # Sort: higher strength first, 4H preferred
    swings_sorted = sorted(
        swings,
        key=lambda x: (x["strength"], 1 if x["tf"] == "4H" else 0),
        reverse=True
    )
    kept = []
    for s in swings_sorted:
        too_close = any(abs(s["price"] - k["price"]) <= tolerance for k in kept)
        if not too_close:
            kept.append(s)
    return sorted(kept, key=lambda x: x["price"], reverse=True)


def _select_display_levels(levels, ltp, atr_5m, n_above=2, n_below=2):
    """
    Select nearest n_above levels above LTP and n_below below LTP.
    Excludes levels within 1x ATR_5min of LTP (too close to act on).
    """
    min_dist = atr_5m

    above = sorted(
        [l for l in levels if l["price"] > ltp and (l["price"] - ltp) >= min_dist and l["strength"] >= 3],
        key=lambda x: x["price"]
    )
    below = sorted(
        [l for l in levels if l["price"] < ltp and (ltp - l["price"]) >= min_dist and l["strength"] >= 3],
        key=lambda x: x["price"],
        reverse=True
    )

    return above[:n_above] + below[:n_below]


# ── combined SR levels (1H swing + 4H swing) ──────────────────────────────

def get_sr_levels(ltp: float) -> list:
    """Legacy wrapper — calls get_combined_sr_levels."""
    return get_combined_sr_levels(ltp)


def get_4h_levels(kite, ltp: float) -> list:
    """Legacy wrapper — returns empty, combined function handles 4H."""
    return []


def get_combined_sr_levels(ltp: float) -> list:
    """
    Main SR level function.
    Detects 1H and 4H swing highs/lows, deduplicates, filters,
    returns nearest 2 above + 2 below LTP.
    Excludes levels within 1x ATR_5min of LTP.
    Cache: SR_LEVELS_CACHE, 300s.
    """
    # Cache hit — recalc side/distance with current LTP
    cached = _cached(_SR_KEY)
    if cached is not None:
        atr_5m   = _get_atr_5m()
        recalced = _recalc(cached, ltp)
        return _select_display_levels(recalced, ltp, atr_5m)

    kite = _kite()
    if kite is None:
        fallback = _last_cached(_SR_KEY) or []
        atr_5m   = _get_atr_5m()
        recalced = _recalc(fallback, ltp)
        return _select_display_levels(recalced, ltp, atr_5m)

    try:
        # Fetch 1H bars — last 30 trading days (~45 calendar days)
        from_dt  = (date.today() - timedelta(days=90)).isoformat()
        to_dt    = date.today().isoformat()
        bars_1h  = kite.historical_data(
            _IDX, from_dt, to_dt, "60minute", continuous=False
        )

        # Fetch daily bars for 4H proxy — last 30 trading days (~50 calendar days)
        bars_4h  = kite.historical_data(
            _IDX, from_dt, to_dt, "day", continuous=False
        )

    except Exception as e:
        print(f"[SR] fetch failed: {e}")
        fallback = _last_cached(_SR_KEY) or []
        _save(_SR_KEY, fallback)
        atr_5m   = _get_atr_5m()
        recalced = _recalc(fallback, ltp)
        return _select_display_levels(recalced, ltp, atr_5m)

    try:
        # ATR 1H (last 20 bars)
        trs_1h = []
        for i in range(1, len(bars_1h)):
            h  = bars_1h[i]["high"]
            l  = bars_1h[i]["low"]
            pc = bars_1h[i - 1]["close"]
            trs_1h.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_1h = sum(trs_1h[-20:]) / min(len(trs_1h), 20) if trs_1h else 184.0

        # ATR 4H/daily (last 14 bars)
        trs_4h = []
        for i in range(1, len(bars_4h)):
            h  = bars_4h[i]["high"]
            l  = bars_4h[i]["low"]
            pc = bars_4h[i - 1]["close"]
            trs_4h.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_4h = sum(trs_4h[-14:]) / min(len(trs_4h), 14) if trs_4h else 356.0

        # ATR 5min
        atr_5m = _get_atr_5m()

        # Find swings
        swings_1h = _find_swing_highs_lows(bars_1h, n=5, atr=atr_1h, tf_label="1H")
        swings_4h = _find_swing_highs_lows(bars_4h, n=3, atr=atr_4h, tf_label="4H")

        # Combine and deduplicate (4H wins within 30pts)
        all_swings = swings_1h + swings_4h
        deduped    = _deduplicate_swings(all_swings, tolerance=30)

        # Save all levels to cache (no distance filter yet)
        # Side/distance added by _recalc at call time
        _save(_SR_KEY, deduped)

        # Select display levels: nearest 2 above + 2 below
        recalced = _recalc(deduped, ltp)
        return _select_display_levels(recalced, ltp, atr_5m)

    except Exception as e:
        print(f"[SR] compute failed: {e}")
        fallback = _last_cached(_SR_KEY) or []
        _save(_SR_KEY, fallback)
        atr_5m   = _get_atr_5m()
        recalced = _recalc(fallback, ltp)
        return _select_display_levels(recalced, ltp, atr_5m)


# ── FVG levels ─────────────────────────────────────────────────────────────

def get_fvg_levels(ltp: float) -> list:
    cached = _cached(_FVG_KEY)
    if cached is not None:
        return cached

    kite = _kite()
    if kite is None:
        return _last_cached(_FVG_KEY) or []

    try:
        from_dt = (date.today() - timedelta(days=5)).isoformat()
        to_dt   = date.today().isoformat()
        bars    = kite.historical_data(
            _IDX, from_dt, to_dt, "5minute", continuous=False
        )
    except Exception as e:
        print(f"[FVG] fetch failed: {e}")
        fallback = _last_cached(_FVG_KEY) or []
        _save(_FVG_KEY, fallback)
        return fallback

    if not bars or len(bars) < 3:
        fallback = _last_cached(_FVG_KEY) or []
        _save(_FVG_KEY, fallback)
        return fallback

    try:
        EXCLUDE_START = {"09:15", "09:20", "09:25"}
        EXCLUDE_END   = {"15:00", "15:05", "15:10", "15:15", "15:20"}

        def _hhmm(b):
            dt = b["date"]
            return dt.strftime("%H:%M") if hasattr(dt, "strftime") else str(dt)[11:16]

        filtered = [
            b for b in bars
            if _hhmm(b) not in EXCLUDE_START and _hhmm(b) not in EXCLUDE_END
        ]

        if len(filtered) < 3:
            return _last_cached(_FVG_KEY) or []

        trs = []
        for i in range(1, len(filtered)):
            h  = filtered[i]["high"]
            l  = filtered[i]["low"]
            pc = filtered[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_5m = sum(trs) / len(trs) if trs else 10.0

        # Save ATR_5m to Redis for SR levels to use
        _r.setex("NIFTY_ATR_5M", 3600, str(round(atr_5m, 2)))

        today_date = date.today()
        fvgs = []

        for i in range(1, len(filtered) - 1):
            c1, c2, c3 = filtered[i - 1], filtered[i], filtered[i + 1]

            c2_bull     = c2["close"] > c2["open"]
            c3_bull     = c3["close"] > c3["open"]
            c3_range    = c3["high"] - c3["low"] + 0.01
            c3_body_pct = abs(c3["close"] - c3["open"]) / c3_range * 100
            same_color  = (c2_bull == c3_bull)
            c3_doji     = c3_body_pct <= 10

            if not same_color and not c3_doji:
                continue

            is_ifvg  = abs(c2["close"] - c2["open"]) >= 0.3 * atr_5m
            bull_gap = c1["high"] < c3["low"]
            bear_gap = c1["low"]  > c3["high"]

            if not bull_gap and not bear_gap:
                continue

            if bull_gap:
                top      = c3["low"]
                bottom   = c1["high"]
                fvg_type = "IFVG Bull" if is_ifvg else "FVG Bull"
            else:
                top      = c1["low"]
                bottom   = c3["high"]
                fvg_type = "IFVG Bear" if is_ifvg else "FVG Bear"

            size_pts = top - bottom
            mid      = (top + bottom) / 2
            size_atr = size_pts / atr_5m if atr_5m else 0

            if size_atr < 0.1:
                strength = 1
            elif size_atr < 0.25:
                strength = 2
            elif size_atr < 0.5:
                strength = 3
            else:
                strength = 4

            c2_dt    = c2["date"]
            bar_date = c2_dt.date() if hasattr(c2_dt, "date") else today_date
            days_old = (today_date - bar_date).days + 1
            if days_old > 3:
                continue

            mitigated = False
            for post in filtered[i + 2:]:
                post_dt   = post["date"]
                post_date = post_dt.date() if hasattr(post_dt, "date") else today_date
                if (post_date - bar_date).days > 3:
                    break
                if bull_gap and post["close"] < mid:
                    mitigated = True
                    break
                if bear_gap and post["close"] > mid:
                    mitigated = True
                    break

            if mitigated:
                continue

            dist = abs(mid - ltp)
            if dist > 400:
                continue

            fvgs.append({
                "type":     fvg_type,
                "top":      round(top, 2),
                "bottom":   round(bottom, 2),
                "size_pts": round(size_pts, 2),
                "strength": strength,
                "days_old": days_old,
                "distance": round(dist, 2),
                "side":     "above" if mid > ltp else "below",
            })

        fvgs.sort(key=lambda x: x["distance"])
        fvgs = fvgs[:4]
        _save(_FVG_KEY, fvgs)
        return fvgs

    except Exception as e:
        print(f"[FVG] compute failed: {e}")
        fallback = _last_cached(_FVG_KEY) or []
        _save(_FVG_KEY, fallback)
        return fallback