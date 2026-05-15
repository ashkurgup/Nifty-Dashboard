"""
========================================================
ROLE: System Health Engine (SOURCE OF TRUTH)

RESPONSIBILITY:
- Compute system health snapshot
- Evaluate Redis, WS, Kite, Session
- Provide UI-ready data for HEADER

SOURCE DEPENDENCIES:
- Redis → heartbeats + auth state
- ws_daemon → writes REDIS_WS_HB
- kite_auth → writes auth (state, token, updated_at)
- session_service → session freshness logic

CONSUMERS:
- core.py → exposes /core/system
- header.html → renders dots

CHANGE POLICY:
- Modify ONLY if health logic or session rules change
========================================================
"""

import time
import redis
import pytz
from datetime import datetime

# ✅ Infra constants
from infra.constants import (
    REDIS_WS_HB
)

# ✅ Central session logic (NEW ✅)
from services.session_service import is_session_fresh
from services.trading_calendar import get_trading_date, get_trading_month

# =========================================================
# REDIS CONNECTION
# =========================================================
r = redis.Redis(
    host="127.0.0.1",
    port=6379,
    decode_responses=True
)

# =========================================================
# CONFIG
# =========================================================
IST = pytz.timezone("Asia/Kolkata")
HEARTBEAT_TIMEOUT = 30
AUTH_KEY = "auth"

print("✅ LOADED system.py FROM:", __file__)


# =========================================================
# ✅ REDIS HEALTH CHECK
# =========================================================
def _redis_reachable() -> bool:
    try:
        r.ping()
        return True
    except Exception:
        return False


# =========================================================
# ✅ MAIN SNAPSHOT FUNCTION
# =========================================================
def snapshot():
    # -----------------------------------------------------
    # TIME CONTEXT
    # -----------------------------------------------------
    now = int(time.time())
    ist_now = datetime.now(IST)

    hour = ist_now.hour
    minute = ist_now.minute

    # ✅ Market session (09:15 – 15:30 IST)
    market_open = (
        (hour > 9 or (hour == 9 and minute >= 15)) and
        (hour < 15 or (hour == 15 and minute < 30))
    )

    # -----------------------------------------------------
    # ✅ AUTH STATE (SOURCE: kite_auth.py)
    # -----------------------------------------------------
    auth = r.hgetall(AUTH_KEY) or {}

    state = auth.get("state", "IDLE")
    token = auth.get("token")
    updated = int(auth.get("updated_at") or 0)

    # ✅ Use shared session logic
    session_fresh = is_session_fresh(auth)

    # ✅ Final kite validity
    kite_valid = bool(
        state == "VALID" and
        token and
        session_fresh
    )

    # -----------------------------------------------------
    # ✅ WS HEALTH (SOURCE: ws_daemon)
    # -----------------------------------------------------
    ws_last_ts = int(r.get(REDIS_WS_HB) or 0)

    if not market_open:
        ws_alive = None
        ws_age_sec = None
    else:
        ws_age_sec = now - ws_last_ts if ws_last_ts else None
        ws_alive = (
            ws_age_sec is not None and
            ws_age_sec <= HEARTBEAT_TIMEOUT
        )

    # -----------------------------------------------------
    # ✅ REDIS HEALTH
    # -----------------------------------------------------
    redis_ok = _redis_reachable()

    # -----------------------------------------------------
    # ✅ FINAL SEMANTIC STATE
    # -----------------------------------------------------
    if not market_open:
        daemon = None
        kite = None
        session = None
    else:
        daemon = ws_alive
        kite = kite_valid
        session = kite_valid

    # -----------------------------------------------------
    # ✅ RETURN SNAPSHOT (USED BY HEADER)
    # -----------------------------------------------------
    return {
        "redis": redis_ok,
        "flask": True,
        "daemon": daemon,
        "kite": kite,
        "session": session,

        # ✅ Debug info
        "auth_state": state,
        "token_age_m": (now - updated) // 60 if updated else 0,
        "last_login_hm": (
            datetime.fromtimestamp(updated, IST).strftime("%H:%M")
            if updated else "--:--"
        ),

        # ✅ Internal diagnostics
        "reachable": {
            "redis": redis_ok,
            "ws": ws_alive if market_open else None,
            "flask": True
        },

        "lag": {
            "ws_sec": ws_age_sec,
            "mode": "LIVE" if market_open else "IDLE"
        },

        # ✅ Market state
        "market": "LIVE" if market_open else "CLOSED",

        # ✅ Active trading date (stays as last trading day over weekends/holidays)
        # Frontend uses this as the single source of truth for "today" in P&L displays.
        "trading_date": get_trading_date()
    }
