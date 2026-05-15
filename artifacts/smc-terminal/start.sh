#!/bin/bash
set -e

cd "$(dirname "$0")"

# Start Redis in the background if not already running
if ! redis-cli ping > /dev/null 2>&1; then
  echo "Starting Redis..."
  redis-server --daemonize yes --loglevel warning
  sleep 1
fi

echo "Redis ready."

export PORT=5000

exec python app.py
