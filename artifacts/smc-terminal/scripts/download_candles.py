"""
Download 3m and 5m NIFTY 50 candle data from 2024-01-01 to yesterday.
Saves to artifacts/smc-terminal/data/nifty_candles.xlsx
"""
import os, sys, time, redis
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from kiteconnect import KiteConnect
import openpyxl

NIFTY_TOKEN = 256265
CHUNK_DAYS  = 60
START_DATE  = date(2024, 1, 1)
END_DATE    = date.today() - timedelta(days=1)
OUT_PATH    = os.path.join(os.path.dirname(__file__), "../data/nifty_candles.xlsx")

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

def fetch_to_sheet(kite, wb, interval, sheet_name):
    ws = wb.create_sheet(sheet_name)
    ws.append(["Date", "Open", "High", "Low", "Close", "Volume"])
    chunks = list(date_chunks(START_DATE, END_DATE))
    total  = 0
    for i, (from_d, to_d) in enumerate(chunks, 1):
        print(f"  [{i}/{len(chunks)}] {from_d} → {to_d} ...", end=" ", flush=True)
        try:
            candles = kite.historical_data(NIFTY_TOKEN, from_d, to_d, interval, continuous=False)
            for c in candles:
                ws.append([c["date"].strftime("%Y-%m-%d %H:%M:%S"),
                            c["open"], c["high"], c["low"], c["close"], c["volume"]])
            total += len(candles)
            print(f"{len(candles)} candles")
        except Exception as e:
            print(f"FAILED — {e}")
        time.sleep(0.4)
    print(f"  ✅ {total} rows written to sheet '{sheet_name}'\n")

if __name__ == "__main__":
    print(f"📅 Range : {START_DATE} → {END_DATE}")
    kite = get_kite()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    print("⬇  Fetching 3-minute candles …")
    fetch_to_sheet(kite, wb, "3minute", "3m")

    print("⬇  Fetching 5-minute candles …")
    fetch_to_sheet(kite, wb, "5minute", "5m")

    wb.save(OUT_PATH)
    print(f"🎉 Saved → {OUT_PATH}")
