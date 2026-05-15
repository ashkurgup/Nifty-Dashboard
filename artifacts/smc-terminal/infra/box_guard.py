"""
Python Box Guard — mirrors the JS window._boxGuard for server-side workers.

Context manager (wrap a loop body or any risky block):
    with box_guard('worker-name'):
        do_something_risky()

Decorator (wrap a whole function):
    @guarded('worker-name')
    def my_fn(): ...

On exception:
  • Prints full traceback to stderr
  • Sends a Telegram alert — rate-limited to 1 per box per 5 minutes via Redis TTL
  • Suppresses the exception so the caller (loop) can continue  (reraise=False default)

Naming convention — use the same name as the frontend data-box attribute where applicable:
  'live-data', 'trade-table', 'pnl', 'alerts'          ← shared with JS side
  'ws-daemon', 'ws-scheduler', 'psych-monitor',         ← server-only
  'eod-summary', 'midnight-cleanup', 'ws-health',
  'alert-queue', 'trade-worker'
"""

import sys
import traceback
import functools

import redis

_r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

_COOLDOWN = 300   # seconds — matches JS frontend cooldown per box


class box_guard:
    """Context manager that catches, reports, and (by default) silences exceptions."""

    def __init__(self, name: str, reraise: bool = False):
        self.name    = name
        self.reraise = reraise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return False                        # no error — pass through

        short_msg = str(exc_val)[:300]
        stack     = traceback.format_exc()

        # Always log locally so workflow console shows it
        print(f"[BOX:{self.name}] {short_msg}", file=sys.stderr)

        # Telegram — one alert per box per COOLDOWN seconds
        key = f"box_err_alert:{self.name}"
        try:
            if not _r.get(key):
                _r.setex(key, _COOLDOWN, "1")
                from ops.telegram_bot import send as _notify
                tg = (
                    f"🚨 <b>BOX MALFUNCTION: {self.name}</b>\n"
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
