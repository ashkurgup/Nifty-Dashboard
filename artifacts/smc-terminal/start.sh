#!/bin/bash
set -e

cd "$(dirname "$0")"

# ── Redis ──────────────────────────────────────────────────
if ! redis-cli ping > /dev/null 2>&1; then
  echo "[SMC] Starting Redis..."
  redis-server --daemonize yes --loglevel warning
  sleep 1
fi
echo "[SMC] Redis ready."

# ── Workers (background) ──────────────────────────────────
python workers/alert_worker.py &
ALERT_PID=$!
echo "[SMC] Alert worker PID=$ALERT_PID"

python workers/trade_worker.py &
TRADE_PID=$!
echo "[SMC] Trade worker PID=$TRADE_PID"

# ── WS daemon restart loop ─────────────────────────────────
# Each KiteTicker run uses Twisted's reactor (singleton — can't restart
# in the same process).  We exit after every disconnect and let this
# loop restart with a fresh process.  Exit 0 = normal close (short
# delay); exit 1 = auth error (longer delay so we don't hammer Kite).
_ws_loop() {
    set +e   # disable errexit — we explicitly handle ws_daemon exit codes
    while true; do
        python ws_daemon.py
        code=$?
        if [ "$code" -eq 1 ]; then
            echo "[SMC] WS daemon exited — auth error, waiting 30s before restart"
            sleep 30
        else
            echo "[SMC] WS daemon exited (code=$code), restarting in 5s..."
            sleep 5
        fi
    done
}
_ws_loop &
WS_PID=$!
echo "[SMC] WS daemon loop PID=$WS_PID"

# ── Cleanup on exit ───────────────────────────────────────
trap "kill $ALERT_PID $TRADE_PID $WS_PID 2>/dev/null; redis-cli shutdown nosave 2>/dev/null" EXIT

# ── Flask (foreground) ────────────────────────────────────
export PORT=5000
export BASE_PATH="/smc"

echo "[SMC] Starting Flask on port $PORT (base path: $BASE_PATH)..."
exec gunicorn wsgi:application \
  --bind "0.0.0.0:$PORT" \
  --workers 1 \
  --timeout 120 \
  --log-level info
