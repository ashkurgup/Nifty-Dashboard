# ops/auto_login.py
# Playwright-based Kite auto-login using system Chromium (NixOS-compatible)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time, redis, pyotp, requests
from kiteconnect import KiteConnect
from ops.telegram_bot import send as notify

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# NixOS system Chromium — properly linked, no missing .so files
_CHROMIUM_CANDIDATES = [
    "/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium",
    "/run/current-system/sw/bin/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

def _find_chromium():
    for path in _CHROMIUM_CANDIDATES:
        if os.path.isfile(path):
            return path
    # Fall back to PATH
    import shutil
    return shutil.which("chromium") or shutil.which("chromium-browser")

def _log(msg):
    """Print to stdout (captured in autologin.log) and flush immediately."""
    print(msg, flush=True)

def run_auto_login():
    auth = r.hgetall("auth") or {}
    if auth.get("state") != "RUNNING":
        _log(f"[auto_login] State is '{auth.get('state')}' (not RUNNING) — exiting early")
        return

    _log("[auto_login] State confirmed RUNNING — starting Playwright login")
    notify("🚀 KITE AUTO-LOGIN INITIATED")

    api_key     = os.getenv("API_KEY")
    username    = os.getenv("KITE_USERNAME")
    password    = os.getenv("KITE_PASSWORD")
    totp_secret = os.getenv("KITE_TOTP_SECRET", "").replace(" ", "")

    if not all([api_key, username, password, totp_secret]):
        _log(f"[auto_login] MISSING env vars — api_key={bool(api_key)} user={bool(username)} pass={bool(password)} totp={bool(totp_secret)}")
        r.hset("auth", "state", "FAILED")
        return

    try:
        from playwright.sync_api import sync_playwright

        chromium_path = _find_chromium()
        _log(f"[auto_login] Chromium path: {chromium_path}")
        if not chromium_path:
            raise Exception("No system Chromium found — cannot auto-login")

        kite = KiteConnect(api_key=api_key)
        login_url = kite.login_url()
        _log(f"[auto_login] Navigating to Kite login…")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                executable_path=chromium_path,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            page = browser.new_page()
            captured_token = [None]

            # ── Monitor ALL requests for request_token= in any URL ──
            # route() only fires for matching path patterns — if Kite's redirect
            # URL differs from expected, it's silently missed.
            # page.on("request") fires for every navigation/request, so we catch
            # request_token= regardless of the callback domain or path.
            def _on_request(request):
                url = request.url
                if "request_token=" in url and captured_token[0] is None:
                    captured_token[0] = url.split("request_token=")[1].split("&")[0]
                    _log(f"[auto_login] Token captured from URL (len={len(captured_token[0])})")

            page.on("request", _on_request)

            try:
                page.goto(login_url, timeout=30000)
                _log("[auto_login] Page loaded — filling credentials")
                page.fill("input#userid", username)
                page.fill("input#password", password)
                page.click("button[type=submit]")

                _log("[auto_login] Credentials submitted — waiting for TOTP field")
                page.wait_for_selector("input[type=number]", timeout=15000)
                totp = pyotp.TOTP(totp_secret).now()
                _log(f"[auto_login] TOTP generated ({totp}) — submitting")
                page.fill("input[type=number]", totp)
                # Explicitly click submit — programmatic fill may not trigger auto-submit
                try:
                    page.click("button[type=submit]", timeout=5000)
                    _log("[auto_login] TOTP submit button clicked")
                except Exception:
                    _log("[auto_login] No submit button found — relying on auto-submit")

                _log("[auto_login] Waiting for Kite callback (any URL with request_token)…")
                deadline = time.time() + 45
                while captured_token[0] is None and time.time() < deadline:
                    time.sleep(0.4)

                if not captured_token[0]:
                    raise Exception("Timed out waiting for Kite callback (45s) — Kite may not have redirected")

                port      = os.getenv("PORT", "5000")
                base_path = os.getenv("BASE_PATH", "")
                resp = requests.get(
                    f"http://127.0.0.1:{port}{base_path}/core/kite-callback?request_token={captured_token[0]}",
                    timeout=15
                )
                _log(f"[auto_login] Local callback HTTP {resp.status_code}")
                notify("✅ LOGIN SUCCESSFUL")
            except Exception as e:
                _log(f"[auto_login] INNER ERROR: {e}")
                notify(f"❌ LOGIN FAILED: {str(e)}")
                r.hset("auth", "state", "FAILED")
            finally:
                browser.close()

    except Exception as e:
        _log(f"[auto_login] OUTER ERROR: {e}")
        notify(f"❌ LOGIN FAILED: {str(e)}")
        r.hset("auth", "state", "FAILED")

if __name__ == "__main__":
    run_auto_login()
