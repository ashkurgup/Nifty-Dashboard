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

python ws_daemon.py &
WS_PID=$!
echo "[SMC] WS daemon PID=$WS_PID"

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
