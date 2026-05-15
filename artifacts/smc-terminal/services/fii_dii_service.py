"""
FII / DII data service.

STRATEGY — accumulation:
  NSE's public API only exposes the current trading day's data.
  Historical endpoints are blocked / session-locked.

  So we store each day's result in a per-date Redis key
  (fii_dii:YYYY-MM-DD, TTL 30 days) as soon as we fetch it.
  The alert worker calls store_today() once per day at 15:40 IST.
  get_fii_dii() assembles the last 5 trading days from those keys.

  Day 1: shows today only.
  After 5 trading days: full 5-day view.
"""
import json
import time
import redis
from datetime import datetime, timedelta
import pytz

_r   = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST = pytz.timezone("Asia/Kolkata")

_DAY_KEY_TTL = 60 * 60 * 24 * 30   # keep each day's data for 30 days
_MAX_DAYS    = 5
_LOOK_BACK   = 14                   # calendar days to scan back for trading days


def _fetch_today_raw() -> list:
    """Fetch current day FII/DII from NSE using cloudscraper."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        scraper.headers.update({
            "Referer":         "https://www.nseindia.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        scraper.get("https://www.nseindia.com", timeout=15)
        time.sleep(1)
        resp = scraper.get(
            "https://www.nseindia.com/api/fiidiiTradeReact",
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[FII/DII] fetch failed: {e}")
        return []


def _parse_day(raw: list) -> dict | None:
    """Extract FII and DII net values from a day's raw response."""
    result = {}
    date_seen = None
    for row in raw:
        date_seen = row.get("date", date_seen)
        cat = (row.get("category", "") or "").upper()
        try:
            net = float(str(row.get("netValue", "0")).replace(",", ""))
        except (ValueError, TypeError):
            net = 0.0
        if "FII" in cat or "FPI" in cat:
            result["fii"] = net
        elif "DII" in cat:
            result["dii"] = net

    if date_seen and ("fii" in result or "dii" in result):
        result["date"] = date_seen
        return result
    return None


def store_today() -> bool:
    """
    Fetch today's FII/DII and save under key fii_dii:YYYY-MM-DD.
    Called by the alert worker once per day at 15:40 IST.
    Returns True if stored successfully.
    """
    raw = _fetch_today_raw()
    if not raw:
        return False

    day = _parse_day(raw)
    if not day:
        return False

    # Derive Redis key from the date NSE returned (e.g. "15-May-2026")
    try:
        dt  = datetime.strptime(day["date"], "%d-%b-%Y")
        key = f"fii_dii:{dt.strftime('%Y-%m-%d')}"
    except Exception:
        today_str = datetime.now(_IST).strftime("%Y-%m-%d")
        key = f"fii_dii:{today_str}"

    _r.setex(key, _DAY_KEY_TTL, json.dumps(day))
    print(f"[FII/DII] stored {key}  FII={day.get('fii')}  DII={day.get('dii')}")
    return True


def get_fii_dii() -> list:
    """
    Return last 5 trading days from accumulated per-date Redis keys.
    Days without data show as None values (frontend renders '—').
    """
    results = []
    today   = datetime.now(_IST).date()

    scanned = 0
    d       = today
    while len(results) < _MAX_DAYS and scanned < _LOOK_BACK:
        # Skip weekends (Saturday=5, Sunday=6)
        if d.weekday() < 5:
            key    = f"fii_dii:{d.strftime('%Y-%m-%d')}"
            stored = _r.get(key)
            if stored:
                try:
                    results.append(json.loads(stored))
                except Exception:
                    pass
            else:
                # Slot exists in the timeline but no data yet
                # Show a placeholder row (frontend renders '—')
                results.append({
                    "date": d.strftime("%d-%b-%Y"),
                    "fii":  None,
                    "dii":  None,
                    "pending": True
                })
        d       -= timedelta(days=1)
        scanned += 1

    return results
