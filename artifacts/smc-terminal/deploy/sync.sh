#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  sync.sh  —  Push latest source files to Digital Ocean
#
#  FIRST TIME: fill in DO_HOST and DO_USER below.
#  EVERY UPDATE: just run  bash deploy/sync.sh
#
#  What it does:
#    1. rsync all source files  (excludes secrets, runtime, cache)
#    2. SSH in and restart the SMC service
#    3. Shows last 20 lines of the service log so you can confirm
# ═══════════════════════════════════════════════════════════

set -e

# ─── CONFIGURE ONCE ────────────────────────────────────────
DO_HOST="YOUR_DROPLET_IP"          # e.g. 159.65.12.34
DO_USER="root"                     # or your sudo user
DO_DIR="/opt/smc-terminal"         # destination on the droplet
SSH_KEY="~/.ssh/id_rsa"            # path to your SSH private key
SERVICE="smc-terminal"             # systemd service name (set in setup_do.sh)
# ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "▶  Syncing $SCRIPT_DIR → $DO_USER@$DO_HOST:$DO_DIR"
echo ""

rsync -avz --progress \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
  --exclude='.env' \
  --exclude='runtime_data/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='venv/' \
  --exclude='dump.rdb' \
  --exclude='*.log' \
  --exclude='deploy/' \
  --exclude='.replit-artifact/' \
  --exclude='public/' \
  --exclude='node_modules/' \
  --delete \
  "$SCRIPT_DIR/" \
  "$DO_USER@$DO_HOST:$DO_DIR/"

echo ""
echo "✅ Files synced."
echo ""
echo "▶  Restarting service on droplet..."

ssh -i "$SSH_KEY" "$DO_USER@$DO_HOST" \
  "systemctl restart $SERVICE && sleep 2 && echo '--- Service Status ---' && systemctl is-active $SERVICE && echo '--- Last 20 log lines ---' && journalctl -u $SERVICE -n 20 --no-pager"

echo ""
echo "✅ Done. SMC Terminal updated on $DO_HOST."
