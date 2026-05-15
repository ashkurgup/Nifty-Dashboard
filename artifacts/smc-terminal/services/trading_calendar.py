"""
Trading Calendar — single source of truth for "what trading day is it?"

get_trading_date() returns the ACTIVE trading date as "YYYY-MM-DD".

Rules:
  - If today (IST) is a trading day  → return today
  - If today is a weekend / holiday  → return the last trading day

Effect on resets:
  Friday trades stay as "today" through Saturday and Sunday.
  The midnight cleanup only fires when the new calendar day IS a trading day,
  so the slate clears at Monday 00:01 IST, not Saturday 00:01 IST.
"""

import pytz
from datetime import datetime, timedelta

IST = pytz.timezone("Asia/Kolkata")

# NSE holidays 2026 — update annually
HOLIDAYS = {
    "2026-01-26",   # Republic Day
    "2026-03-06",   # Mahashivratri (observed)
    "2026-03-20",   # Holi
    "2026-04-01",   # Good Friday (alternate)
    "2026-04-14",   # Dr Ambedkar Jayanti / Baisakhi
    "2026-05-01",   # Maharashtra Day
    "2026-05-28",   # Buddha Purnima
    "2026-10-02",   # Gandhi Jayanti
    "2026-11-05",   # Diwali (Laxmi Pujan)
    "2026-12-25",   # Christmas
}


def is_trading_day(d) -> bool:
    """Return True if `d` (date or datetime) is an NSE trading day."""
    return d.weekday() < 5 and d.strftime("%Y-%m-%d") not in HOLIDAYS


def get_trading_date() -> str:
    """
    Return the active trading date as 'YYYY-MM-DD' (IST).

    On a trading day   → today's date.
    On a non-trading day (weekend / holiday) → the most recent trading day.
    """
    now = datetime.now(IST)
    d = now.date()

    # Walk backwards until we land on a trading day
    while not is_trading_day(d):
        d -= timedelta(days=1)

    return d.strftime("%Y-%m-%d")


def get_trading_month() -> str:
    """Return 'YYYY-MM' of the active trading date."""
    return get_trading_date()[:7]
