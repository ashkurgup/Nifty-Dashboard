import sys
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import time
import json
import redis
from dotenv import load_dotenv
from kiteconnect import KiteTicker

load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("API_KEY")

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

AUTH_KEY = "auth"
HEARTBEAT_KEY = "ws_heartbeat"
TRADE_KEY = "active_session_trades"

NIFTY_TOKEN = 256265
SENSEX_TOKEN = 265


def get_access_token():
    auth = r.hgetall(AUTH_KEY) or {}
    return auth.get("token")


def get_tokens():
    tokens = {NIFTY_TOKEN, SENSEX_TOKEN}

    try:
        raw = r.get(TRADE_KEY)
        if raw:
            trades = json.loads(raw)
            for t in trades:
                if t.get("status") == "ACTIVE" and t.get("token"):
                    tokens.add(int(t["token"]))
    except Exception as e:
        print("⚠️ token build error:", e)

    return list(tokens)


def run_ws():
    while True:
        try:
            auth = r.hgetall(AUTH_KEY) or {}

            if auth.get("state") != "VALID":
                print("⏳ waiting for valid session...")
                time.sleep(3)
                continue

            token = auth.get("token")

            if not token:
                time.sleep(3)
                continue

            print("🚀 connecting WS...")

            time.sleep(2)  # ✅ stabilization

            kws = KiteTicker(API_KEY, token)

            def on_connect(ws, response):
                tokens = get_tokens()
                print("✅ subscribed to", len(tokens), "tokens")

                ws.subscribe(tokens)
                ws.set_mode(ws.MODE_FULL, tokens)

            def on_ticks(ws, ticks):
                for t in ticks:
                    token = t["instrument_token"]
                    ltp = t.get("last_price")

                    if ltp is not None:
                        r.set(f"ltp:{token}", ltp)

                r.set(HEARTBEAT_KEY, int(time.time()), ex=30)

            def on_close(ws, code, reason):
                print("⚠️ closed:", code)

            def on_error(ws, code, reason):
                print("❌ error:", code)

            kws.on_connect = on_connect
            kws.on_ticks = on_ticks
            kws.on_close = on_close
            kws.on_error = on_error

            kws.connect(threaded=False)

        except Exception as e:
            print("❌ crash:", e)

        print("🔁 reconnecting...")
        time.sleep(3)


if __name__ == "__main__":
    run_ws()

