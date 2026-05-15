# ops/auto_login.py
import os, time, redis, pyotp, requests, subprocess
from playwright.sync_api import sync_playwright
from kiteconnect import KiteConnect
from ops.telegram_bot import send as notify

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

def run_auto_login():
    auth = r.hgetall("auth") or {}
    if auth.get("state") != "RUNNING": return

    notify("🚀 KITE AUTO-LOGIN INITIATED")
    kite = KiteConnect(api_key=os.getenv("API_KEY"))
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        try:
            page.goto(kite.login_url())
            page.fill("input#userid", os.getenv("KITE_USERNAME"))
            page.fill("input#password", os.getenv("KITE_PASSWORD"))
            page.click("button[type=submit]")
            
            page.wait_for_selector("input[type=number]")
            totp = pyotp.TOTP(os.getenv("KITE_TOTP_SECRET").replace(" ", "")).now()
            page.fill("input[type=number]", totp)
            
            page.wait_for_url(lambda u: "request_token=" in u, timeout=30000)
            token = page.url.split("request_token=")[1].split("&")[0]
            
            # Force local callback to establish session
            port = os.getenv("PORT", "5000")
            base_path = os.getenv("BASE_PATH", "")
            requests.get(f"http://127.0.0.1:{port}{base_path}/core/kite-callback?request_token={token}")
            notify("✅ LOGIN SUCCESSFUL")
        except Exception as e:
            notify(f"❌ LOGIN FAILED: {str(e)}")
            r.hset("auth", "state", "FAILED")
        finally:
            browser.close()

if __name__ == "__main__":
    run_auto_login()
