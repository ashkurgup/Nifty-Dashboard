"""
Download 3m and 5m NIFTY 50 candle data from 2024-01-01 to yesterday.
Saves to artifacts/smc-terminal/data/candles_3m.csv and candles_5m.csv

Kite API limit: max 60 days per request for intraday intervals.
Run: python artifacts/smc-terminal/scripts/download_candles.py
"""
import os, sys, time, csv, redis
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from kiteconnect import KiteConnect

NIFTY_TOKEN = 256265
CHUNK_DAYS  = 60
START_DATE  = date(2024, 1, 1)
END_DATE    = date.today() - timedelta(days=1)
OUT_DIR     = os.path.join(os.path.dirname(__file__), "../data")

def get_kite():
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    auth = r.hgetall("auth") or {}
    token = auth.get("access_token")
    if not token:
        sys.exit("❌ No valid access_token in Redis. Login to Kite first.")
    kite = KiteConnect(api_key=os.getenv("API_KEY"))
    kite.set_access_token(token)
    return kite

def date_chunks(start, end, chunk=CHUNK_DAYS):
    cur = start
    while cur <= end:
        yield cur, min(cur + timedelta(days=chunk - 1), end)
        cur += timedelta(days=chunk)

def fetch_interval(kite, interval, filename):
    out_path = os.path.join(OUT_DIR, filename)
    os.makedirs(OUT_DIR, exist_ok=True)
    chunks = list(date_chunks(START_DATE, END_DATE))
    total  = 0

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "open", "high", "low", "close", "volume"])

        for i, (from_d, to_d) in enumerate(chunks, 1):
            print(f"  [{i}/{len(chunks)}] {from_d} → {to_d} ...", end=" ", flush=True)
            try:
                candles = kite.historical_data(
                    NIFTY_TOKEN, from_d, to_d, interval, continuous=False
                )
                for c in candles:
                    writer.writerow([
                        c["date"].strftime("%Y-%m-%d %H:%M:%S"),
                        c["open"], c["high"], c["low"], c["close"], c["volume"]
                    ])
                total += len(candles)
                print(f"{len(candles)} candles")
            except Exception as e:
                print(f"FAILED — {e}")
            time.sleep(0.4)   # stay within Kite rate limits

    print(f"  ✅ Saved {total} rows → {out_path}\n")
    return total

if __name__ == "__main__":
    print(f"📅 Range : {START_DATE} → {END_DATE}")
    print(f"📁 Output: {OUT_DIR}\n")

    kite = get_kite()

    print("⬇  Fetching 3-minute candles …")
    fetch_interval(kite, "3minute", "candles_3m.csv")

    print("⬇  Fetching 5-minute candles …")
    fetch_interval(kite, "5minute", "candles_5m.csv")

    print("🎉 Done.")
