import sys
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import time
import json
import subprocess
import redis
from dotenv import load_dotenv
from kiteconnect import KiteTicker, KiteConnect
from candle_manager import update_nifty_stats

load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("API_KEY")

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

AUTH_KEY      = "auth"
HEARTBEAT_KEY = "ws_heartbeat"
TRADE_KEY     = "active_session_trades"

NIFTY_TOKEN  = 256265
SENSEX_TOKEN = 265

# Zerodha auth-failure close codes
AUTH_CLOSE_CODES = {807, 0}


def get_tokens():
    tokens = {NIFTY_TOKEN, SENSEX_TOKEN}
    try:
        raw = r.get(TRADE_KEY)
        if raw:
            for t in json.loads(raw):
                if t.get("status") == "ACTIVE" and t.get("token"):
                    tokens.add(int(t["token"]))
    except Exception as e:
        print("⚠️ token build error:", e)
    return list(tokens)


def _trigger_auto_relogin(reason="session expired"):
    """Set state RUNNING and spawn Playwright auto-login subprocess."""
    print(f"🔑 Triggering auto re-login — {reason}")
    try:
        from ops.telegram_bot import send as notify
        notify(f"⚡ Kite session lost ({reason}) — auto-reconnecting...")
    except Exception:
        pass
    r.hset(AUTH_KEY, mapping={"state": "RUNNING", "updated_at": int(time.time())})
    subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "ops/auto_login.py")])


def _is_token_still_valid(access_token):
    """Quick REST check — returns True if token is still accepted by Kite."""
    try:
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        kite.profile()
        return True
    except Exception:
        return False


def run_ws():
    consecutive_quick_closes = [0]   # mutable so closures can update it

    while True:
        try:
            auth  = r.hgetall(AUTH_KEY) or {}
            state = auth.get("state", "IDLE")

            # ── State: FAILED → auto-relogin immediately ──────────────────
            if state == "FAILED":
                _trigger_auto_relogin("state=FAILED")
                time.sleep(45)      # give Playwright time to finish
                continue

            # ── State: not yet VALID → keep waiting ───────────────────────
            if state != "VALID":
                print("⏳ waiting for valid session...")
                time.sleep(3)
                continue

            access_token = auth.get("token")
            if not access_token:
                time.sleep(3)
                continue

            print("🚀 connecting WS...")
            ws_started_at = time.time()
            auth_error_on_close = [False]

            kws = KiteTicker(API_KEY, access_token)

            def on_connect(ws, response):
                consecutive_quick_closes[0] = 0        # reset streak on good connect
                tokens = get_tokens()
                ws.subscribe(tokens)
                ws.set_mode(ws.MODE_FULL, tokens)
                print("✅ subscribed to", len(tokens), "tokens")

                # Cache PDC (Previous Day Close) once per session
                try:
                    kite = KiteConnect(api_key=API_KEY)
                    kite.set_access_token(access_token)
                    ohlc = kite.ohlc(["NSE:NIFTY 50"])
                    pdc  = ohlc["NSE:NIFTY 50"]["ohlc"]["close"]
                    r.set("NIFTY_PDC", pdc)
                    print(f"✅ PDC cached: {pdc}")
                except Exception as e:
                    print(f"⚠️ PDC fetch failed: {e}")

            def on_ticks(ws, ticks):
                for tick in ticks:
                    tick_token = tick["instrument_token"]
                    ltp = tick.get("last_price")
                    if ltp is not None:
                        r.set(f"ltp:{tick_token}", ltp)
                    if tick_token == NIFTY_TOKEN and ltp:
                        update_nifty_stats(ltp)
                r.set(HEARTBEAT_KEY, int(time.time()), ex=30)

            def on_close(ws, code, reason):
                print(f"⚠️ WS closed  code={code}  reason={reason}")
                if code in AUTH_CLOSE_CODES or \
                   "not authorised" in str(reason).lower() or \
                   "access token" in str(reason).lower():
                    auth_error_on_close[0] = True

            def on_error(ws, code, reason):
                print(f"❌ WS error  code={code}  reason={reason}")

            kws.on_connect = on_connect
            kws.on_ticks   = on_ticks
            kws.on_close   = on_close
            kws.on_error   = on_error

            kws.connect(threaded=False)          # blocks until WS closes

            # ── Post-disconnect analysis ───────────────────────────────────
            uptime = time.time() - ws_started_at

            if auth_error_on_close[0]:
                print("🔑 Auth error on close — marking FAILED")
                r.hset(AUTH_KEY, "state", "FAILED")
                consecutive_quick_closes[0] = 0
                time.sleep(2)
                continue

            if uptime < 30:
                consecutive_quick_closes[0] += 1
                print(f"⚡ Quick close ({uptime:.1f}s)  streak={consecutive_quick_closes[0]}")
                if consecutive_quick_closes[0] >= 3:
                    # Three quick closes in a row → stale token
                    print("🔑 3 quick closes — validating token...")
                    if not _is_token_still_valid(access_token):
                        print("🔑 Token invalid — marking FAILED")
                        r.hset(AUTH_KEY, "state", "FAILED")
                    consecutive_quick_closes[0] = 0
                    time.sleep(2)
                    continue
            else:
                consecutive_quick_closes[0] = 0

        except Exception as e:
            print("❌ crash:", e)

        print("🔁 reconnecting in 3s...")
        time.sleep(3)


if __name__ == "__main__":
    run_ws()
