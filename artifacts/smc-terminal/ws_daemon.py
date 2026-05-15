import sys
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import time
import json
import threading
import subprocess
import redis
import pytz
from datetime import datetime
from dotenv import load_dotenv
from kiteconnect import KiteTicker, KiteConnect
from candle_manager import update_nifty_stats, update_sensex_stats

load_dotenv(os.path.join(BASE_DIR, ".env"))

API_KEY = os.getenv("API_KEY")

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

AUTH_KEY      = "auth"
HEARTBEAT_KEY = "ws_heartbeat"
TRADE_KEY     = "active_session_trades"

NIFTY_TOKEN  = 256265
SENSEX_TOKEN = 265

AUTH_CLOSE_CODES = {807, 0}

IST = pytz.timezone("Asia/Kolkata")

# ── Shared flag so the scheduler doesn't re-trigger while a login is running ──
_login_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    """Mark state RUNNING and spawn Playwright auto-login subprocess."""
    if not _login_lock.acquire(blocking=False):
        print(f"🔑 Re-login already in progress — skipping ({reason})")
        return
    try:
        print(f"🔑 Triggering auto re-login — {reason}")
        try:
            from ops.telegram_bot import send as notify
            notify(f"⚡ Kite re-login triggered ({reason})")
        except Exception:
            pass
        r.hset(AUTH_KEY, mapping={"state": "RUNNING", "updated_at": int(time.time())})
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "ops/auto_login.py")]
        )
        proc.wait(timeout=90)          # wait up to 90s for Playwright to finish
    except Exception as e:
        print(f"⚠️ auto-login subprocess error: {e}")
        r.hset(AUTH_KEY, "state", "FAILED")
    finally:
        _login_lock.release()


def _is_token_still_valid(access_token):
    try:
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        kite.profile()
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Daily scheduler — re-login every morning at 8:28 AM IST
# ─────────────────────────────────────────────────────────────────────────────

def _daily_login_scheduler():
    """
    Runs as a daemon thread.
    At 8:28 AM IST every day, force a fresh Kite login so the token is always
    valid before market opens at 9:15 AM.
    """
    triggered_today = [None]   # tracks the date of last scheduled trigger

    while True:
        try:
            now  = datetime.now(IST)
            date = now.date()

            # Trigger window: 8:28–8:30 AM IST
            if now.hour == 8 and 28 <= now.minute <= 30:
                if triggered_today[0] != date:
                    triggered_today[0] = date
                    print(f"⏰ Daily scheduled re-login at {now.strftime('%H:%M IST')}")
                    # Force invalidate current session so run_ws picks it up
                    r.hset(AUTH_KEY, "state", "FAILED")
            time.sleep(30)
        except Exception as e:
            print(f"⚠️ scheduler error: {e}")
            time.sleep(30)


# ─────────────────────────────────────────────────────────────────────────────
#  Main WebSocket loop
# ─────────────────────────────────────────────────────────────────────────────

def run_ws():
    consecutive_quick_closes = [0]
    relogin_attempts  = [0]       # consecutive failed login attempts
    last_relogin_at   = [0.0]     # timestamp of last login attempt

    RELOGIN_COOLDOWN  = 5 * 60    # 5 minutes between attempts
    MAX_RELOGIN_TRIES = 5         # alert and pause after this many failures

    while True:
        try:
            auth  = r.hgetall(AUTH_KEY) or {}
            state = auth.get("state", "IDLE")

            # ── IDLE / FAILED → re-login with cooldown ────────────────────
            if state in ("IDLE", "FAILED"):
                now = time.time()
                since_last = now - last_relogin_at[0]

                # Enforce cooldown between attempts
                if since_last < RELOGIN_COOLDOWN:
                    wait = int(RELOGIN_COOLDOWN - since_last)
                    print(f"⏳ Login cooldown — {wait}s remaining (attempt {relogin_attempts[0]})")
                    time.sleep(min(30, wait))
                    continue

                # Too many consecutive failures → alert, long pause
                if relogin_attempts[0] >= MAX_RELOGIN_TRIES:
                    print(f"❌ {MAX_RELOGIN_TRIES} consecutive login failures — pausing 30 min")
                    try:
                        from ops.telegram_bot import send as notify
                        notify(f"❌ Auto-login failed {MAX_RELOGIN_TRIES}x. Use ⚠️ MANUAL LOGIN.")
                    except Exception:
                        pass
                    time.sleep(30 * 60)
                    relogin_attempts[0] = 0
                    continue

                last_relogin_at[0] = time.time()
                relogin_attempts[0] += 1
                reason = "startup" if state == "IDLE" else f"FAILED attempt {relogin_attempts[0]}"
                print(f"🔑 Attempting login ({reason})...")
                _trigger_auto_relogin(reason)
                continue

            # ── RUNNING → login in progress, wait ─────────────────────────
            if state == "RUNNING":
                print("⏳ Login in progress...")
                time.sleep(5)
                continue

            # ── VALID → connect WebSocket ──────────────────────────────────
            relogin_attempts[0] = 0     # reset failure counter on successful session
            access_token = auth.get("token")
            if not access_token:
                time.sleep(3)
                continue

            print("🚀 Connecting WS...")
            ws_started_at = time.time()
            auth_error_on_close = [False]

            kws = KiteTicker(API_KEY, access_token)

            def on_connect(ws, response):
                consecutive_quick_closes[0] = 0
                tokens = get_tokens()
                ws.subscribe(tokens)
                ws.set_mode(ws.MODE_FULL, tokens)
                print("✅ Subscribed to", len(tokens), "tokens")

                # Cache PDC for both NIFTY and SENSEX once per session
                try:
                    kite = KiteConnect(api_key=API_KEY)
                    kite.set_access_token(access_token)
                    ohlc = kite.ohlc(["NSE:NIFTY 50", "BSE:SENSEX"])
                    nifty_pdc  = ohlc["NSE:NIFTY 50"]["ohlc"]["close"]
                    sensex_pdc = ohlc["BSE:SENSEX"]["ohlc"]["close"]
                    r.set("NIFTY_PDC",  nifty_pdc)
                    r.set("SENSEX_PDC", sensex_pdc)
                    print(f"✅ PDC cached — NIFTY: {nifty_pdc}  SENSEX: {sensex_pdc}")
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
                    elif tick_token == SENSEX_TOKEN and ltp:
                        update_sensex_stats(ltp)
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

            kws.connect(threaded=False)

            # ── Post-disconnect analysis ───────────────────────────────────
            uptime = time.time() - ws_started_at

            if auth_error_on_close[0]:
                print("🔑 Auth error on close — marking FAILED")
                r.hset(AUTH_KEY, "state", "FAILED")
                consecutive_quick_closes[0] = 0
                continue

            if uptime < 30:
                consecutive_quick_closes[0] += 1
                print(f"⚡ Quick close ({uptime:.1f}s)  streak={consecutive_quick_closes[0]}")
                if consecutive_quick_closes[0] >= 3:
                    print("🔑 3 quick closes — validating token...")
                    if not _is_token_still_valid(access_token):
                        print("🔑 Token invalid — marking FAILED")
                        r.hset(AUTH_KEY, "state", "FAILED")
                    consecutive_quick_closes[0] = 0
                    continue
            else:
                consecutive_quick_closes[0] = 0

        except Exception as e:
            print("❌ crash:", e)

        print("🔁 Reconnecting in 3s...")
        time.sleep(3)


if __name__ == "__main__":
    # Start daily 8:28 AM IST scheduler as daemon thread
    scheduler = threading.Thread(target=_daily_login_scheduler, daemon=True)
    scheduler.start()
    print("⏰ Daily login scheduler started (fires at 08:28 IST)")

    run_ws()
