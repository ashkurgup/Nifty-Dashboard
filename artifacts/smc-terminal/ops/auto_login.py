# ops/auto_login.py
# Pure-requests Kite auto-login (no Playwright/Chromium needed)
import sys, os
# Ensure the smc-terminal root is on sys.path when run as a subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time, redis, pyotp, requests
from kiteconnect import KiteConnect
from ops.telegram_bot import send as notify

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

def run_auto_login():
    auth = r.hgetall("auth") or {}
    if auth.get("state") != "RUNNING": return

    notify("🚀 KITE AUTO-LOGIN INITIATED")
    api_key    = os.getenv("API_KEY")
    username   = os.getenv("KITE_USERNAME")
    password   = os.getenv("KITE_PASSWORD")
    totp_secret = os.getenv("KITE_TOTP_SECRET", "").replace(" ", "")

    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
            "X-Kite-Version": "3",
        })

        # Step 1: POST credentials
        resp = s.post(
            "https://kite.zerodha.com/api/login",
            data={"user_id": username, "password": password},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise Exception(f"Login failed: {data.get('message', data)}")
        request_id = data["data"]["request_id"]

        # Step 2: POST TOTP
        totp_val = pyotp.TOTP(totp_secret).now()
        resp = s.post(
            "https://kite.zerodha.com/api/twofa",
            data={
                "user_id": username,
                "request_id": request_id,
                "twofa_value": totp_val,
                "twofa_type": "totp",
            },
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise Exception(f"2FA failed: {data.get('message', data)}")

        # Step 3: Follow Kite Connect OAuth redirect chain to capture request_token
        kite = KiteConnect(api_key=api_key)
        login_url = kite.login_url()

        # Walk redirects manually until we hit the callback URL with request_token
        current_url = login_url
        request_token = None
        for _ in range(10):
            resp = s.get(current_url, allow_redirects=False, timeout=15)
            location = resp.headers.get("Location", "")
            if "request_token=" in location:
                request_token = location.split("request_token=")[1].split("&")[0]
                break
            if "request_token=" in current_url:
                request_token = current_url.split("request_token=")[1].split("&")[0]
                break
            if resp.status_code in (301, 302, 303, 307, 308) and location:
                current_url = location
            else:
                break

        if not request_token:
            raise Exception("Could not capture request_token from Kite redirect chain")

        # Step 4: Call local callback to establish session in Redis
        port = os.getenv("PORT", "5000")
        base_path = os.getenv("BASE_PATH", "")
        callback_url = f"http://127.0.0.1:{port}{base_path}/core/kite-callback?request_token={request_token}"
        requests.get(callback_url, timeout=10)

        notify("✅ LOGIN SUCCESSFUL")

    except Exception as e:
        notify(f"❌ LOGIN FAILED: {str(e)}")
        r.hset("auth", "state", "FAILED")

if __name__ == "__main__":
    run_auto_login()
