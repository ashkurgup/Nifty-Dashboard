# workers/alert_worker.py
import sys
import os
import time
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from infra import redis_bus as rbus
from infra.constants import REDIS_NOTIFY_QUEUE
from services.alert_service import check_alerts  # Your existing service
from services.psychology_service import check_psychology_triggers, send_eod_summary # New service
from ops.telegram_bot import send as notify

def process_alert(alert):
    try:
        # Handling for your existing manual price alerts
        msg = f"🔔 <b>Price Target Hit</b>\nSymbol: {alert.get('symbol')}\nTarget: {alert.get('target')}"
        notify(msg)
    except Exception as e:
        print(f"[ALERT PROCESS ERROR] {e}")

def run():
    print("🚀 Master Alert Worker Started")
    queue = REDIS_NOTIFY_QUEUE
    last_eod_check = ""

    while True:
        try:
            # 1. RUN DISCIPLINE & PNL MONITORING
            check_psychology_triggers()
            
            # 2. EOD SUMMARY (Triggered at 3:35 PM IST)
            now = time.strftime("%H:%M")
            if now == "15:35" and last_eod_check != now:
                send_eod_summary()
                last_eod_check = now

            # 3. RUN EXISTING PRICE ALERTS (Wait for Queue)
            job = rbus.queue_pop(queue, timeout=5)
            if job:
                if job.get("type") == "alert":
                    # Check against your existing manual price alerts
                    check_alerts(job["symbol"], job["ltp"])
                    process_alert(job)

        except Exception as e:
            print(f"[WORKER ERROR] {e}")
            time.sleep(2)

if __name__ == "__main__":
    run()
