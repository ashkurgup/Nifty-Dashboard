import os
import json
import redis
from kiteconnect import KiteConnect

# =========================================================
# CONFIG
# =========================================================
API_KEY = os.getenv("API_KEY")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime_data/instruments.json")

# ✅ Redis (your actual auth source)
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

AUTH_KEY = "auth"

# =========================================================
# GET TOKEN FROM REDIS ✅
# =========================================================
auth = r.hgetall(AUTH_KEY) or {}
access_token = auth.get("token")

if not access_token:
    print("❌ No access_token found in Redis. Login first.")
    exit(1)

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(access_token)

# =========================================================
# FETCH INSTRUMENTS
# =========================================================
try:
    print("[INFO] Fetching instruments (NFO & BFO)...")

    nfo = kite.instruments("NFO")
    bfo = kite.instruments("BFO")

    all_data = nfo + bfo

    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_data, f, default=str)

    print(f"✅ Saved {len(all_data)} instruments → {OUTPUT_FILE}")

except Exception as e:
    print("❌ Error:", e)
