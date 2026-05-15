"""
ROLE: Authentication Gateway (Kite Trading Session)
"""
import os
import sys
import time
import redis
import subprocess
from flask import Blueprint, request, redirect, session

from kiteconnect import KiteConnect
from services.session_service import is_session_fresh
from ops.telegram_bot import send as notify

AUTH_KEY = "auth"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

auth_gateway_blueprint = Blueprint("kite_auth", __name__)

@auth_gateway_blueprint.route("/trigger-login")
def trigger_login():
    """Existing Auto-Refresh route with SMC Gate protection"""
    if not session.get("terminal_unlocked"): return redirect("/login")
    
    try:
        auth = r.hgetall(AUTH_KEY) or {}
        state = auth.get("state", "IDLE")

        if state == "VALID" and is_session_fresh(auth):
            session["authorized"] = True
            return redirect("/")

        if state == "RUNNING": return redirect("/")

        r.hset(AUTH_KEY, mapping={"state": "RUNNING", "updated_at": int(time.time())})

        try:
            notify("🚀 Kite Auto-login triggered")
            subprocess.Popen([
                sys.executable,
                os.path.join(BASE_DIR, "ops/auto_login.py")
            ])
        except Exception as e:
            print("Execution error:", e)

        return redirect("/")
    except Exception as e:
        return redirect("/")

@auth_gateway_blueprint.route("/kite-login-url")
def kite_login_url():
    """Return Kite login URL as JSON so JS can open it in a new tab"""
    if not session.get("terminal_unlocked"):
        from flask import jsonify
        return jsonify({"error": "not_unlocked"}), 403
    from flask import jsonify
    kite = KiteConnect(api_key=os.getenv("API_KEY"))
    return jsonify({"url": kite.login_url()})

@auth_gateway_blueprint.route("/manual-kite-login")
def manual_kite_login():
    """Manual backup route — opens Kite login in new tab, user pastes token back"""
    if not session.get("terminal_unlocked"): return redirect("/login")
    kite = KiteConnect(api_key=os.getenv("API_KEY"))
    return redirect(kite.login_url())

@auth_gateway_blueprint.route("/submit-token", methods=["POST"])
def submit_token():
    """Accept a manually-pasted request_token and establish Kite session"""
    from flask import jsonify, request as freq
    if not session.get("terminal_unlocked"):
        return jsonify({"status": "error", "message": "Not unlocked"}), 403
    try:
        request_token = freq.json.get("request_token", "").strip()
        if not request_token:
            return jsonify({"status": "error", "message": "Empty token"}), 400
        import time as _time
        kite = KiteConnect(api_key=os.getenv("API_KEY"))
        data = kite.generate_session(request_token, api_secret=os.getenv("API_SECRET"))
        r.hset(AUTH_KEY, mapping={
            "state": "VALID",
            "token": data["access_token"],
            "updated_at": int(_time.time())
        })
        session["authorized"] = True
        notify("✅ Kite session established via manual token")

        # Refresh instruments in background
        try:
            from ops.fetch_instruments import fetch_and_save
            import services.instrument_lookup as il
            fetch_and_save(data["access_token"])
            il._data = None          # force cache reload on next request
        except Exception as fe:
            print("⚠️ Instrument fetch failed:", fe)

        return jsonify({"status": "ok"})
    except Exception as e:
        r.hset(AUTH_KEY, "state", "FAILED")
        return jsonify({"status": "error", "message": str(e)}), 500

@auth_gateway_blueprint.route("/kite-callback")
def kite_callback():
    try:
        request_token = request.args.get("request_token")
        kite = KiteConnect(api_key=os.getenv("API_KEY"))
        data = kite.generate_session(request_token, api_secret=os.getenv("API_SECRET"))

        r.hset(AUTH_KEY, mapping={
            "state": "VALID",
            "token": data["access_token"],
            "updated_at": int(time.time())
        })

        session["authorized"] = True
        notify("✅ Kite session established")

        # Refresh instruments in background
        try:
            from ops.fetch_instruments import fetch_and_save
            import services.instrument_lookup as il
            fetch_and_save(data["access_token"])
            il._data = None          # force cache reload on next request
        except Exception as fe:
            print("⚠️ Instrument fetch failed:", fe)

        return redirect("/")
    except Exception as e:
        r.hset(AUTH_KEY, "state", "FAILED")
        return redirect("/")
