#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  setup_do.sh  —  First-time Digital Ocean server setup
#
#  Run this ONCE on a fresh Ubuntu 22.04 droplet:
#    scp deploy/setup_do.sh root@YOUR_IP:/tmp/
#    ssh root@YOUR_IP "bash /tmp/setup_do.sh"
#
#  After this completes:
#    • SMC Terminal runs as a systemd service  (smc-terminal)
#    • Nginx proxies  /smc  →  localhost:5000
#    • Redis runs on 127.0.0.1:6379
#    • Playwright browsers installed
#
#  Then push your code with:
#    bash deploy/sync.sh
#  And create your .env:
#    ssh root@YOUR_IP "nano /opt/smc-terminal/.env"
# ═══════════════════════════════════════════════════════════

set -e

APP_DIR="/opt/smc-terminal"
SERVICE="smc-terminal"
PYTHON="python3"

echo "=== [1/7] System packages ==="
apt-get update -qq
apt-get install -y -qq \
  python3 python3-pip python3-venv \
  redis-server nginx \
  git curl wget unzip \
  chromium-browser \
  libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
  libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2

echo "=== [2/7] Enable Redis on startup ==="
systemctl enable redis-server
systemctl start redis-server

echo "=== [3/7] Create app directory ==="
mkdir -p "$APP_DIR/runtime_data"
touch "$APP_DIR/runtime_data/.gitkeep"

echo "=== [4/7] Python venv + dependencies ==="
# (Run this step again after each sync if requirements.txt changes)
$PYTHON -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
if [ -f "$APP_DIR/requirements.txt" ]; then
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
  echo "  requirements.txt installed"
else
  echo "  ⚠️  requirements.txt not found yet — run after first sync"
fi

echo "=== [5/7] Playwright browsers ==="
"$APP_DIR/venv/bin/playwright" install chromium --with-deps || \
  echo "  ⚠️  Playwright install needs requirements.txt first — re-run after sync"

echo "=== [6/7] systemd service ==="
cat > "/etc/systemd/system/$SERVICE.service" << 'EOF'
[Unit]
Description=SMC Terminal
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/smc-terminal
EnvironmentFile=/opt/smc-terminal/.env
Environment=PORT=5000
Environment=BASE_PATH=/smc
ExecStart=/opt/smc-terminal/venv/bin/gunicorn wsgi:application \
          --bind 0.0.0.0:5000 \
          --workers 1 \
          --timeout 120 \
          --log-level info
ExecStartPost=/bin/bash -c 'sleep 2 && /opt/smc-terminal/venv/bin/python workers/alert_worker.py &'
ExecStartPost=/bin/bash -c 'sleep 2 && /opt/smc-terminal/venv/bin/python workers/trade_worker.py &'
ExecStartPost=/bin/bash -c 'sleep 2 && /opt/smc-terminal/venv/bin/python ws_daemon.py &'
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE"

echo "=== [7/7] Nginx config ==="
cat > "/etc/nginx/sites-available/smc" << 'EOF'
server {
    listen 80;
    server_name _;

    location /smc {
        proxy_pass         http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_read_timeout 120;
        proxy_send_timeout 120;
    }
}
EOF

ln -sf /etc/nginx/sites-available/smc /etc/nginx/sites-enabled/smc
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "════════════════════════════════════════════════"
echo "✅  Server setup complete."
echo ""
echo "  NEXT STEPS:"
echo "  1. Push code from Replit:   bash deploy/sync.sh"
echo "  2. Create .env on droplet:  ssh root@IP 'nano /opt/smc-terminal/.env'"
echo "     Required env vars:"
echo "       API_KEY=..."
echo "       API_SECRET=..."
echo "       FLASK_SECRET=..."
echo "       SESSION_SECRET=..."
echo "       SITE_PASSWORD=..."
echo "       KITE_USERNAME=..."
echo "       KITE_PASSWORD=..."
echo "       KITE_TOTP_SECRET=..."
echo "       TELEGRAM_BOT_TOKEN=..."
echo "       TELEGRAM_CHAT_ID=..."
echo "       DATABASE_ID=..."
echo "       NOTION_TOKEN=..."
echo "  3. Start service:           systemctl start smc-terminal"
echo "  4. Check logs:              journalctl -u smc-terminal -f"
echo "════════════════════════════════════════════════"
