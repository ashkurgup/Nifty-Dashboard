import json
import redis
from infra.constants import REDIS_TRADES

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)


def get_trades():
    raw = r.get(REDIS_TRADES) or "[]"
    return json.loads(raw)


def save_trades(trades):
    r.set(REDIS_TRADES, json.dumps(trades))


def open_trade(trade):
    trades = get_trades()
    trades.append(trade)
    save_trades(trades)
    return trade


def close_trade(trade_id, exit_price, timestamp):
    trades = get_trades()

    for t in trades:
        if t["id"] == trade_id:
            t["status"] = "CLOSED"
            t["exit_price"] = exit_price   # ✅ FIXED
            t["exit_time"] = timestamp

    save_trades(trades)
