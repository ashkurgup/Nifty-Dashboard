import os
import requests
import signal
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_SHUTTING_DOWN = False

def _shutdown_handler(signum, frame):
    global _SHUTTING_DOWN
    _SHUTTING_DOWN = True

signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)


def send(text: str):
    if _SHUTTING_DOWN:
        return  # ✅ silently ignore during shutdown

    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram Config Missing")
        return

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram Error]: {e}")

