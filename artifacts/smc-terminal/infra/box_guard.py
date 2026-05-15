"""
Python Box Guard — catches exceptions, logs locally, and optionally sends Telegram.

Context manager:
    with box_guard('ws-daemon'):
        risky_work()

Decorator:
    @guarded('ws-daemon')
    def my_fn(): ...

─── CRITICALITY ─────────────────────────────────────────────────────────────
Only boxes listed in CRITICAL_BOXES send a Telegram alert.
Everything else is logged to stderr only — no noise.

Add a name here when a failure in that component means live trading is at risk.
Remove it when you decide it's acceptable background noise.
─────────────────────────────────────────────────────────────────────────────
"""

import sys
import traceback
import functools

import redis

_r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

_COOLDOWN = 300   # seconds between repeated alerts for the same box

# ─── EDIT THIS LIST to control which failures ping you ───────────────────────
CRITICAL_BOXES = {
    'ws-daemon',        # WebSocket process crashed unexpectedly
    'ws-ticks',         # Tick handler broke — live price data lost
    'ws-scheduler',     # Daily 8:28 AM re-login scheduler died
    'midnight-cleanup', # Trade data cleanup failed — data integrity at risk
    'trade-worker',     # Trade excursion worker down — PnL tracking broken
}
# ─────────────────────────────────────────────────────────────────────────────


class box_guard:
    """Context manager that catches, reports, and (by default) silences exceptions."""

    def __init__(self, name: str, reraise: bool = False):
        self.name    = name
        self.reraise = reraise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return False                         # no error — pass through

        short_msg = str(exc_val)[:300]
        stack     = traceback.format_exc()

        # Always log locally so the workflow console captures it
        print(f"[BOX:{self.name}] {short_msg}", file=sys.stderr)

        # Telegram only for critical boxes
        if self.name in CRITICAL_BOXES:
            key = f"box_err_alert:{self.name}"
            try:
                if not _r.get(key):
                    _r.setex(key, _COOLDOWN, "1")
                    from ops.telegram_bot import send as _notify
                    tg = (
                        f"🚨 <b>CRITICAL FAILURE: {self.name}</b>\n"
                        f"<code>{short_msg}</code>\n\n"
                        f"<pre>{stack[-500:]}</pre>"
                    )
                    _notify(tg)
            except Exception as te:
                print(f"[BOX:{self.name}] telegram send failed: {te}", file=sys.stderr)

        return not self.reraise   # True → suppress;  False → re-raise


def guarded(name: str, reraise: bool = False):
    """Decorator version of box_guard — wraps an entire function."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with box_guard(name, reraise=reraise):
                return fn(*args, **kwargs)
        return wrapper

    return decorator
