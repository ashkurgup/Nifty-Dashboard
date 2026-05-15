"""
Persistent trade store — Redis as fast cache, disk as durable backing.
All reads/writes go through here so trades survive workflow restarts.
"""
import json
import os
import time
import redis

TRADE_KEY  = "active_session_trades"
STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "runtime_data", "trades.json")

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)


def _ensure_dir():
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)


def load_from_disk():
    """Load trades from disk into Redis (called once on startup)."""
    _ensure_dir()
    if not os.path.exists(STORE_PATH):
        return
    try:
        with open(STORE_PATH) as f:
            trades = json.load(f)
        r.set(TRADE_KEY, json.dumps(trades))
        print(f"✅ Trade store: loaded {len(trades)} trades from disk")
    except Exception as e:
        print(f"⚠️ Trade store: failed to load from disk — {e}")


def get_trades() -> list:
    """Read from Redis; bootstrap from disk if Redis is empty."""
    raw = r.get(TRADE_KEY)
    if raw:
        return json.loads(raw)
    # Redis cold-start — try disk
    load_from_disk()
    raw = r.get(TRADE_KEY)
    return json.loads(raw) if raw else []


def save_trades(trades: list):
    """Write to Redis AND disk atomically."""
    payload = json.dumps(trades)
    r.set(TRADE_KEY, payload)
    _ensure_dir()
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(payload)
    os.replace(tmp, STORE_PATH)   # atomic on POSIX


def midnight_cleanup():
    """
    Remove CLOSED trades from a previous day.
    Active trades from any date are kept — they carry over until manually exited.
    """
    trades = get_trades()
    today  = time.strftime("%Y-%m-%d")
    before = len(trades)
    # Keep: every ACTIVE trade (any date) + today's CLOSED trades
    trades = [t for t in trades
              if t.get("status") == "ACTIVE" or t.get("date") == today]
    after = len(trades)
    save_trades(trades)
    print(f"🌙 Midnight cleanup: removed {before - after} old closed trades, {after} remaining")
    return before - after
