# workers/alert_worker.py
import sys
import os
import time
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from infra import redis_bus as rbus
from infra.constants import REDIS_NOTIFY_QUEUE
from services.alert_service import check_alerts
from services.psychology_service import check_psychology_triggers, send_eod_summary
from services.trade_store import midnight_cleanup
from ops.telegram_bot import send as notify

def process_alert(alert):
    try:
        msg = f"🔔 <b>Price Target Hit</b>\nSymbol: {alert.get('symbol')}\nTarget: {alert.get('target')}"
        notify(msg)
    except Exception as e:
        print(f"[ALERT PROCESS ERROR] {e}")

def run():
    print("🚀 Master Alert Worker Started")
    queue = REDIS_NOTIFY_QUEUE
    last_eod_check    = ""
    last_midnight_run = ""
    last_health_check = 0

    import redis as _redis
    r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

    while True:
        try:
            # 1. DISCIPLINE & PNL MONITORING
            check_psychology_triggers()

            now_hhmm = time.strftime("%H:%M")
            today    = time.strftime("%Y-%m-%d")

            # 2. EOD SUMMARY (3:35 PM IST)
            if now_hhmm == "15:35" and last_eod_check != today:
                send_eod_summary()
                last_eod_check = today

            # 3. MIDNIGHT CLEANUP (00:01 IST) — remove old closed trades, keep active
            if now_hhmm == "00:01" and last_midnight_run != today:
                removed = midnight_cleanup()
                last_midnight_run = today
                notify(f"🌙 Midnight cleanup: {removed} old closed trades removed. Active trades carried forward.")

            # 4. WS HEALTH CHECK — every 5 minutes
            now_ts = int(time.time())
            if now_ts - last_health_check >= 300:
                last_health_check = now_ts
                try:
                    auth_state = r.hget("auth", "state") or "IDLE"
                    hb_raw     = r.get("ws_heartbeat")
                    hb_stale   = (not hb_raw) or (now_ts - int(hb_raw)) > 90
                    if auth_state in ("FAILED", "IDLE") and hb_stale:
                        print(f"🔧 Health check: state={auth_state}, heartbeat stale — attempting recovery")
                        from services.auth_store import try_recover
                        if not try_recover(r, "auth"):
                            # Disk token expired — reset so ws_daemon retries Playwright
                            r.hset("auth", "state", "IDLE")
                            print("🔧 Health check: disk token invalid — reset to IDLE for ws_daemon")
                        else:
                            print("🔧 Health check: disk token valid — recovered session")
                except Exception as he:
                    print(f"[HEALTH CHECK ERROR] {he}")

            # 5. PRICE ALERTS from queue
            job = rbus.queue_pop(queue, timeout=5)
            if job:
                if job.get("type") == "alert":
                    check_alerts(job["symbol"], job["ltp"])
                    process_alert(job)

        except Exception as e:
            print(f"[WORKER ERROR] {e}")
            time.sleep(2)

if __name__ == "__main__":
    run()
