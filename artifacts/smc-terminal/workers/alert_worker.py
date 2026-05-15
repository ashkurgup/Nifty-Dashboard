# workers/alert_worker.py
import sys
import os
import time
import pytz
from datetime import datetime as _dt
_IST = pytz.timezone("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from infra import redis_bus as rbus
from infra.constants import REDIS_NOTIFY_QUEUE, TELEGRAM_COOLDOWN_SECONDS
from infra.box_guard import box_guard
from services.alert_service import check_alerts
from services.psychology_service import check_psychology_triggers, send_eod_summary
from services.trade_store import midnight_cleanup
from ops.telegram_bot import send as notify

def process_alert(alert):
    with box_guard('alert-process'):
        import redis as _r2
        _rc = _r2.Redis(host="127.0.0.1", port=6379, decode_responses=True)
        cooldown_key = f"tg_alert:{alert.get('symbol')}:{alert.get('target')}"
        if _rc.get(cooldown_key):
            return  # same price target already notified within 30 hours
        msg = f"🔔 <b>Price Target Hit</b>\nSymbol: {alert.get('symbol')}\nTarget: {alert.get('target')}"
        notify(msg)
        _rc.set(cooldown_key, "1", ex=TELEGRAM_COOLDOWN_SECONDS)

def run():
    print("🚀 Master Alert Worker Started")
    queue = REDIS_NOTIFY_QUEUE
    last_eod_check    = ""
    last_midnight_run = ""
    last_health_check = 0

    import redis as _redis
    r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

    while True:

        # ── 1. DISCIPLINE & PNL MONITORING ────────────────────────────────
        with box_guard('psych-monitor'):
            check_psychology_triggers()

        # ── Time context (outside any guard so always available) ──────────
        try:
            now_ist  = _dt.now(_IST)
            now_hhmm = now_ist.strftime("%H:%M")
            today    = now_ist.strftime("%Y-%m-%d")
        except Exception:
            time.sleep(2)
            continue

        # ── 2. EOD SUMMARY (3:35 PM IST) ──────────────────────────────────
        with box_guard('eod-summary'):
            if now_hhmm == "15:35" and last_eod_check != today:
                send_eod_summary()
                last_eod_check = today

        # ── 3. MIDNIGHT CLEANUP — only fires on actual trading days ───────
        with box_guard('midnight-cleanup'):
            if now_hhmm == "00:01" and last_midnight_run != today:
                from services.trading_calendar import is_trading_day
                from datetime import date as _date_cls
                if is_trading_day(_date_cls.fromisoformat(today)):
                    removed = midnight_cleanup()
                    last_midnight_run = today
                    notify(f"🌙 Midnight cleanup: {removed} old closed trades removed. Active trades carried forward.")

        # ── 4. WS HEALTH CHECK — every 30 minutes ─────────────────────────
        with box_guard('ws-health'):
            now_ts = int(time.time())
            if now_ts - last_health_check >= 1800:
                last_health_check = now_ts
                auth_state = r.hget("auth", "state") or "IDLE"
                hb_raw     = r.get("ws_heartbeat")
                hb_stale   = (not hb_raw) or (now_ts - int(hb_raw)) > 90
                if auth_state in ("FAILED", "IDLE") and hb_stale:
                    print(f"🔧 Health check: state={auth_state}, heartbeat stale — attempting recovery")
                    from services.auth_store import try_recover
                    if not try_recover(r, "auth"):
                        r.hset("auth", "state", "IDLE")
                        print("🔧 Health check: disk token invalid — reset to IDLE for ws_daemon")
                    else:
                        print("🔧 Health check: disk token valid — recovered session")

        # ── 5. PRICE ALERTS from queue ─────────────────────────────────────
        with box_guard('alert-queue'):
            job = rbus.queue_pop(queue, timeout=5)
            if job:
                if job.get("type") == "alert":
                    check_alerts(job["symbol"], job["ltp"])
                    process_alert(job)

if __name__ == "__main__":
    run()
