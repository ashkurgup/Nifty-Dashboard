"""
FII / DII data fetcher — pulls from NSE public API.

Uses cloudscraper to handle Cloudflare bot protection (NSE blocks plain requests).
Caches result in Redis for 1 hour — NSE only publishes new data after ~17:30 IST.
Falls back to last cached value if NSE is unreachable.
"""
import json
import time
import redis

_r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

_CACHE_KEY     = "fii_dii_data"
_CACHE_TTL     = 3600   # 1 hour
_STALE_KEY     = "fii_dii_stale"
_STALE_TTL     = 86400  # keep last-known data for 24 hours as fallback
_MAX_DAYS      = 5


def _fetch_from_nse() -> list:
    """Fetch raw FII/DII records from NSE using cloudscraper (Cloudflare-safe)."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        scraper.headers.update({
            "Referer":         "https://www.nseindia.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # Warm-up: visit homepage to get cookies
        scraper.get("https://www.nseindia.com", timeout=15)
        time.sleep(1)

        resp = scraper.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    except Exception as e:
        print(f"[FII/DII] NSE fetch failed: {e}")
        return []


def _parse(raw: list) -> list:
    """
    Group NSE response by date, extract FII and DII net values.
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
    """
    Return last 5 trading days of FII/DII data.
    Priority: fresh cache → fetch NSE → stale cache → empty.
    """
    # 1. Fresh cache hit
    cached = _r.get(_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # 2. Fetch live
    raw    = _fetch_from_nse()
    result = _parse(raw) if raw else []

    if result:
        # Store fresh + stale copies
        _r.setex(_CACHE_KEY, _CACHE_TTL,  json.dumps(result))
        _r.setex(_STALE_KEY, _STALE_TTL,  json.dumps(result))
        return result

    # 3. Fall back to stale data (yesterday's values, better than nothing)
    stale = _r.get(_STALE_KEY)
    if stale:
        try:
            return json.loads(stale)
        except Exception:
            pass

    return []
