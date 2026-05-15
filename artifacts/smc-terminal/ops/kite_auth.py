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

@auth_gateway_blueprint.route("/manual-kite-login")
def manual_kite_login():
    """Existing Manual backup route with SMC Gate protection"""
    if not session.get("terminal_unlocked"): return redirect("/login")
    kite = KiteConnect(api_key=os.getenv("API_KEY"))
    return redirect(kite.login_url())

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
        return redirect("/")
    except Exception as e:
        r.hset(AUTH_KEY, "state", "FAILED")
        return redirect("/")
