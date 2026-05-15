"""
Downloads NFO instruments from Kite and saves to runtime_data/instruments.json.
Called automatically after every successful login.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import date
from kiteconnect import KiteConnect

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_PATH = os.path.join(BASE_DIR, "runtime_data", "instruments.json")

TRACKED_INDICES = {"NIFTY", "BANKNIFTY", "MIDCPNIFTY", "FINNIFTY"}
OPTION_TYPES    = {"CE", "PE"}


def _serialize(obj):
    """JSON serializer for date objects returned by KiteConnect."""
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def fetch_and_save(access_token: str) -> int:
    """
    Fetch NFO instruments using the given access_token, filter to
    tracked index options, and persist to SAVE_PATH.
    Returns the count of saved records.
    """
    api_key = os.getenv("API_KEY")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    print("📥 Fetching NFO instruments from Kite...")
    all_instruments = kite.instruments("NFO")

    filtered = [
        i for i in all_instruments
        if i.get("name") in TRACKED_INDICES
        and i.get("instrument_type") in OPTION_TYPES
    ]

    os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)

    with open(SAVE_PATH, "w") as f:
        json.dump(filtered, f, default=_serialize)

    print(f"✅ Saved {len(filtered)} instruments → {SAVE_PATH}")
    return len(filtered)


if __name__ == "__main__":
    import redis
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    token = (r.hgetall("auth") or {}).get("token")
    if not token:
        print("❌ No valid token in Redis")
        sys.exit(1)
    fetch_and_save(token)
