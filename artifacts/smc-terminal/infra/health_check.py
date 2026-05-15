"""
========================================================
STATUS: FROZEN
ROLE: Infrastructure Health Monitor
RESPONSIBILITY:
- Continuously evaluate system health
- Send Telegram alerts on state change
- Send ONE startup confirmation message
CHANGE POLICY:
- Modify ONLY if health model or alerting rules change
LAST REVIEWED: 2026-05-12
========================================================
"""

import time
import signal
import redis

from system import snapshot
from ops.telegram_bot import send

# -------------------------------------------------------
# Process lifecycle handling
# -------------------------------------------------------
RUNNING = True

def shutdown(signum, frame):
    global RUNNING
    RUNNING = False
    print("🛑 Health monitor shutting down gracefully")

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# -------------------------------------------------------
# Redis (explicit, though snapshot handles most logic)
# -------------------------------------------------------
r = redis.Redis(
    host="127.0.0.1",
    port=6379,
    decode_responses=True
)

# -------------------------------------------------------
# State tracking
# -------------------------------------------------------
LAST_STATE = None
STARTUP_ALERT_SENT = False

def state_string(s):
    return (
        f"Redis: {'OK' if s['redis'] else 'DOWN'}\n"
        f"Flask: {'OK' if s['flask'] else 'DOWN'}\n"
        f"Daemon: {'OK' if s['daemon'] else 'DOWN'}\n"
        f"Kite: {'VALID' if s['kite'] else 'INVALID'}"
    )

# -------------------------------------------------------
# Main loop
# -------------------------------------------------------
def main():
    global LAST_STATE, STARTUP_ALERT_SENT

    print("🩺 Health monitor started")

    while RUNNING:
        try:
            s = snapshot()

            current = (
                s["redis"],
                s["flask"],
                s["daemon"],
                s["kite"]
            )

            # ✅ One-time startup confirmation (guaranteed Telegram)
            if not STARTUP_ALERT_SENT:
                STARTUP_ALERT_SENT = True
                if all(current):
                    send(
                        "🩺 HEALTH MONITOR ONLINE\n\n"
                        "All core services are UP and being monitored."
                    )
                else:
                    send(
                        "🟡 HEALTH MONITOR ONLINE (PARTIAL)\n\n"
                        + state_string(s)
                    )
                LAST_STATE = current
                time.sleep(2)
                continue

            # ✅ State-change alerting
            if current != LAST_STATE:
                healthy = all(current)

                if healthy:
                    send(
                        "🟢 SYSTEM RECOVERED\n\n"
                        "All core services operational."
                    )
                else:
                    send(
                        "🔴 SYSTEM DEGRADED\n\n"
                        + state_string(s)
                    )

                LAST_STATE = current

        except Exception as e:
            print(f"[HEALTH ERROR] {e}")

        time.sleep(10)

# -------------------------------------------------------
# Entrypoint
# -------------------------------------------------------
if __name__ == "__main__":
    main()
