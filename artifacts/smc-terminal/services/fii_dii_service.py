"""
FII / DII data fetcher — pulls from NSE public API, caches in Redis for 60 min.
NSE updates this data once per day after market close (~17:30 IST).
"""
import json
import time
import redis

_r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

_CACHE_KEY = "fii_dii_data"
_CACHE_TTL = 3600          # 1 hour — data only changes once a day
_MAX_DAYS  = 5

_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}


def _fetch_from_nse() -> list:
    """Fetch raw FII/DII records from NSE. Returns [] on any error."""
    import requests
    try:
        s = requests.Session()
        s.headers.update(_HEADERS)

        # Warm up session (NSE requires a cookie from the homepage)
        s.get("https://www.nseindia.com", timeout=12)
        time.sleep(0.5)

        resp = s.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            timeout=12
        )
        resp.raise_for_status()
        return resp.json()

    except Exception as e:
        print(f"[FII/DII] NSE fetch failed: {e}")
        return []


def _parse(raw: list) -> list:
    """
    Group by date, extract FII and DII net values.
    Returns list of dicts sorted newest-first, capped at _MAX_DAYS.
    """
    grouped: dict[str, dict] = {}

    for row in raw:
        date = row.get("date", "")
        cat  = (row.get("category", "") or "").upper()
        try:
            net = float(str(row.get("netValue", "0")).replace(",", ""))
        except (ValueError, TypeError):
            net = 0.0

        if date not in grouped:
            grouped[date] = {"date": date, "fii": None, "dii": None}

        if "FII" in cat or "FPI" in cat:
            grouped[date]["fii"] = net
        elif "DII" in cat:
            grouped[date]["dii"] = net

    # Sort newest first (NSE dates are like "15-May-2026")
    try:
        from datetime import datetime
        sorted_dates = sorted(
            grouped.keys(),
            key=lambda d: datetime.strptime(d, "%d-%b-%Y"),
            reverse=True
        )
    except Exception:
        sorted_dates = list(grouped.keys())

    return [grouped[d] for d in sorted_dates[:_MAX_DAYS]]


def get_fii_dii() -> list:
    """Return last 5 trading days of FII/DII data (cached)."""
    cached = _r.get(_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    raw    = _fetch_from_nse()
    result = _parse(raw) if raw else []

    if result:
        _r.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(result))

    return result
