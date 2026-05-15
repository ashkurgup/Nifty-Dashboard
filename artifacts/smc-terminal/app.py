import os
import redis
from flask import Flask, render_template, session, redirect, request
from dotenv import load_dotenv

from ops.kite_auth import auth_gateway_blueprint
from core import core as terminal_core_blueprint
from quick_trade import quick_trade_blueprint
from ops.system import snapshot

from infra.constants import REDIS_FLASK_HB
from infra import redis_bus as rbus

# ===============================
# ENV & INIT
# ===============================
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)
# Using SITE_PASSWORD as the fallback for secret_key if FLASK_SECRET is missing
app.secret_key = os.getenv("FLASK_SECRET", os.getenv("SITE_PASSWORD"))

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# ===============================
# BLUEPRINTS
# ===============================
app.register_blueprint(auth_gateway_blueprint, url_prefix="/core")
app.register_blueprint(terminal_core_blueprint, url_prefix="/core")
app.register_blueprint(quick_trade_blueprint, url_prefix="/core")

# ===============================
# SMC GATE (WEBSITE ACCESS)
# ===============================
@app.route("/login", methods=["GET", "POST"])
def terminal_login():
    """Gate 1: Website access using your login.html template"""
    if request.method == "POST":
        # UPDATED: Now matches your .env variable name SITE_PASSWORD
        if request.form.get("password") == os.getenv("SITE_PASSWORD"):
            session["terminal_unlocked"] = True
            return redirect("/")
        else:
            # Optional: You can add an error message here if the password fails
            print("❌ Invalid SITE_PASSWORD attempt")
            
    return render_template("login.html")

# ===============================
# MAIN DASHBOARD ROUTE
# ===============================
@app.route("/")
def index():
    # 1. Check SMC Gate (Website Access Password)
    if not session.get("terminal_unlocked"):
        return redirect("/login")

    # 2. Sync Kite Auth State from Redis for indicators
    auth = r.hgetall("auth") or {}
    if auth.get("state") == "VALID":
        session["authorized"] = True

    rbus.heartbeat(REDIS_FLASK_HB)
    stats = snapshot()

    return render_template("index.html", **stats)

# ===============================
# ENTRY
# ===============================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
