"""
SR Levels and FVG detection for Nifty 50.

SR Levels:
  Clusters 1H swing highs/lows from last ~15 trading days.
  ATR-based zone tolerance. Max 8 levels within 400 pts of LTP.
  Cache: SR_LEVELS_CACHE, 300 s.

FVG Levels:
  Detects bullish/bearish Fair Value Gaps in 5m bars, last 3 trading days.
  Excludes first 3 and last 5 bars of each session.
  IFVG when c2 body >= 0.3 * ATR_5m.
  Non-mitigated only. Within 400 pts of LTP. Max 4, sorted by distance.
  Cache: FVG_CACHE, 300 s.
"""
import os
import json
import redis
import pytz
from datetime import datetime, date, timedelta

_r   = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST = pytz.timezone("Asia/Kolkata")
_IDX = 256265

_SR_KEY = "SR_LEVELS_CACHE"
_FVG_KEY = "FVG_CACHE"
_TTL = 300


def _kite():
    auth = _r.hgetall("auth") or {}
    if auth.get("state") != "VALID" or not auth.get("token"):
        return None
    from kiteconnect import KiteConnect
    k = KiteConnect(api_key=os.getenv("API_KEY"))
    k.set_access_token(auth["token"])
    return k


def _cached(key):
    raw = _r.get(key)
    if not raw:
        return None
    try:
        d = json.loads(raw)
        if (datetime.now().timestamp() - d.get("_ts", 0)) < _TTL:
            return d.get("data")
    except Exception:
        pass
    return None


def _save(key, data):
    payload = json.dumps({"_ts": datetime.now().timestamp(), "data": data})
    _r.setex(key, _TTL + 60, payload)


def _last_cached(key):
    raw = _r.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw).get("data")
    except Exception:
        return None


def get_sr_levels(ltp: float) -> list:
    cached = _cached(_SR_KEY)
    if cached is not None:
        return cached

    kite = _kite()
    if kite is None:
        return _last_cached(_SR_KEY) or []

    try:
        from_dt = (date.today() - timedelta(days=22)).isoformat()
        to_dt   = date.today().isoformat()
        bars    = kite.historical_data(_IDX, from_dt, to_dt, "60minute", continuous=False)
    except Exception as e:
        print(f"[SR] fetch failed: {e}")
        fallback = _last_cached(_SR_KEY) or []
        _save(_SR_KEY, fallback)
        return fallback

    if not bars or len(bars) < 2:
        fallback = _last_cached(_SR_KEY) or []
        _save(_SR_KEY, fallback)
        return fallback

    try:
        trs = []
        for i in range(1, len(bars)):
            h  = bars[i]["high"]
            l  = bars[i]["low"]
            pc = bars[i - 1]["close"]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_1h = sum(trs[-20:]) / min(len(trs), 20) if trs else 30.0
        zone = max(18.0, 0.1 * atr_1h)

        prices = []
        for b in bars:
            prices.append(b["high"])
            prices.append(b["low"])
        prices.sort()

        clusters = []
        for p in prices:
            merged = False
            for c in clusters:
                if abs(p - sum(c) / len(c)) <= zone:
                    c.append(p)
                    merged = True
                    break
            if not merged:
                clusters.append([p])

        levels = []
        for c in clusters:
            if len(c) < 3:
                continue
            lvl = sum(c) / len(c)
            if abs(lvl - ltp) > 400:
                continue
            strength = 2 if len(c) == 3 else (3 if len(c) == 4 else 4)
            levels.append({
                "price":    round(lvl, 2),
                "type":     "1H Swing",
                "strength": strength,
                "distance": round(abs(lvl - ltp), 2),
                "side":     "above" if lvl > ltp else "below",
            })

        levels.sort(key=lambda x: x["price"], reverse=True)
        levels = levels[:8]
        _save(_SR_KEY, levels)
        return levels

    except Exception as e:
        print(f"[SR] compute failed: {e}")
        fallback = _last_cached(_SR_KEY) or []
        _save(_SR_KEY, fallback)
        return fallback


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
        bars    = kite.historical_data(_IDX, from_dt, to_dt, "5minute", continuous=False)
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

        today_date = date.today()
        fvgs = []

        for i in range(1, len(filtered) - 1):
            c1, c2, c3 = filtered[i - 1], filtered[i], filtered[i + 1]

            c2_bull       = c2["close"] > c2["open"]
            c3_bull       = c3["close"] > c3["open"]
            c3_range      = c3["high"] - c3["low"] + 0.01
            c3_body_pct   = abs(c3["close"] - c3["open"]) / c3_range * 100
            same_color    = (c2_bull == c3_bull)
            c3_doji       = c3_body_pct <= 10

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
