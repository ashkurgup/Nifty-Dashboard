import json
import redis
import pytz
from datetime import datetime, timedelta
from flask import Blueprint, jsonify

from infra.constants import REDIS_NIFTY_SPOT, REDIS_SENSEX_SPOT

quick_trade_blueprint = Blueprint("quick_trade", __name__)
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
IST = pytz.timezone("Asia/Kolkata")

HOLIDAYS = [
    "2026-01-26", "2026-03-06", "2026-03-20", "2026-04-01",
    "2026-04-14", "2026-05-01", "2026-05-28", "2026-10-02",
    "2026-11-05", "2026-12-25"
]

def get_adjusted_expiry(target_weekday, current_time):
    days_ahead = (target_weekday - current_time.weekday() + 7) % 7
    if days_ahead == 0 and current_time.time() > datetime.strptime("15:30", "%H:%M").time():
        days_ahead = 7

    expiry = (current_time + timedelta(days=days_ahead)).date()
    while expiry.strftime("%Y-%m-%d") in HOLIDAYS or expiry.weekday() >= 5:
        expiry -= timedelta(days=1)

    return expiry.strftime("%Y-%m-%d")

@quick_trade_blueprint.route("/detect_params")
def detect_params():
    try:
        nifty_raw = r.get(REDIS_NIFTY_SPOT)
        sensex_raw = r.get(REDIS_SENSEX_SPOT)

        nifty_spot = float(json.loads(nifty_raw).get("lp", 0)) if nifty_raw else 0
        sensex_spot = float(json.loads(sensex_raw).get("lp", 0)) if sensex_raw else 0

        nifty_atm = int(round(nifty_spot / 50) * 50) if nifty_spot else 0
        sensex_atm = int(round(sensex_spot / 100) * 100) if sensex_spot else 0

        now = datetime.now(IST)

        return jsonify({
            "status": "SUCCESS",
            "nifty_spot": nifty_spot,
            "nifty_atm": nifty_atm,
            "nifty_expiry": get_adjusted_expiry(1, now),
            "sensex_spot": sensex_spot,
            "sensex_atm": sensex_atm,
            "sensex_expiry": get_adjusted_expiry(3, now),
            "server_time": now.strftime("%H:%M:%S")
        })
    except Exception as e:
        return jsonify({"status": "ERROR", "msg": str(e)}), 500

