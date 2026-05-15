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

NFO_INDICES  = {"NIFTY", "BANKNIFTY", "MIDCPNIFTY", "FINNIFTY"}
BFO_INDICES  = {"SENSEX", "BANKEX"}
OPTION_TYPES = {"CE", "PE"}


def _serialize(obj):
    """JSON serializer for date objects returned by KiteConnect."""
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def fetch_and_save(access_token: str) -> int:
    """
    Fetch NFO + BFO instruments, filter to tracked index options,
    and persist to SAVE_PATH. Returns the count of saved records.
    """
    api_key = os.getenv("API_KEY")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    print("📥 Fetching NFO instruments from Kite...")
    nfo = kite.instruments("NFO")
    nfo_filtered = [
        i for i in nfo
        if i.get("name") in NFO_INDICES
        and i.get("instrument_type") in OPTION_TYPES
    ]

    print("📥 Fetching BFO instruments from Kite...")
    bfo = kite.instruments("BFO")
    bfo_filtered = [
        i for i in bfo
        if i.get("name") in BFO_INDICES
        and i.get("instrument_type") in OPTION_TYPES
    ]

    filtered = nfo_filtered + bfo_filtered

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
