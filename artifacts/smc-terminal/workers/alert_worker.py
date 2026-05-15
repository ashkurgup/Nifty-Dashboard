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
from services.candle_exporter import generate_candle_excel, get_public_url
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

            # 4. EOD KITE DATA (3:45 PM IST) — generate candle Excel + send download link
            if now_hhmm == "15:45" and last_eod_check != today:
                try:
                    path = generate_candle_excel(today)
                    url  = get_public_url(path)
                    notify(
                        f"📊 <b>Today's Kite Data Ready</b>\n"
                        f"Date: {today}\n"
                        f"⬇ <a href='{url}'>Download Excel</a>\n"
                        f"(NIFTY + SENSEX — 1min &amp; 5min candles)"
                    )
                    print(f"✅ EOD candle file generated: {path}")
                except Exception as ce:
                    notify(f"⚠️ EOD candle export failed: {ce}")
                    print(f"⚠️ EOD candle export failed: {ce}")

            # 4. PRICE ALERTS from queue
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
