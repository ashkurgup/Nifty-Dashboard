import os
import re
import redis
from flask import Flask, render_template, session, redirect, request, g
from dotenv import load_dotenv

from ops.kite_auth import auth_gateway_blueprint
from core import core as terminal_core_blueprint
from quick_trade import quick_trade_blueprint
from ops.system import snapshot
from services.trade_store import load_from_disk as _load_trades_from_disk

from infra.constants import REDIS_FLASK_HB
from infra import redis_bus as rbus

# ===============================
# ENV & INIT
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BASE_PATH = os.getenv("BASE_PATH", "").rstrip("/")

from datetime import timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", os.getenv("SITE_PASSWORD", "dev-secret"))
app.permanent_session_lifetime = timedelta(days=30)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# ===============================
# BLUEPRINTS
# ===============================
app.register_blueprint(auth_gateway_blueprint, url_prefix="/core")
app.register_blueprint(terminal_core_blueprint, url_prefix="/core")
app.register_blueprint(quick_trade_blueprint, url_prefix="/core")

# ── Restore persisted trades from disk on every startup ──────────────────
_load_trades_from_disk()

@app.context_processor
def inject_globals():
    return {"BASE_PATH": BASE_PATH}

@app.after_request
def no_cache(response):
    if "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ===============================
# PREFIX MIDDLEWARE
# Handles /smc prefix: strips it from incoming requests,
# rewrites redirects and HTML fetch() calls on the way out.
# ===============================
class PrefixMiddleware:
    def __init__(self, wsgi_app, prefix):
        self.app = wsgi_app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        prefix = self.prefix

        if prefix:
            if path == prefix or path.startswith(prefix + "/"):
                environ["PATH_INFO"] = path[len(prefix):] or "/"
                environ["SCRIPT_NAME"] = prefix
            else:
                from werkzeug.exceptions import NotFound
                return NotFound()(environ, start_response)

        collected = []

        def capture_start_response(status, headers, exc_info=None):
            # Fix Location header on redirects — handles both relative and absolute URLs
            from urllib.parse import urlparse, urlunparse
            new_headers = []
            for name, value in headers:
                if name.lower() == "location" and prefix:
                    parsed = urlparse(value)
                    rpath = parsed.path
                    # Add prefix if path doesn't already have it
                    if rpath.startswith("/") and not rpath.startswith(prefix + "/") and rpath != prefix:
                        new_path = prefix + rpath
                        value = urlunparse(parsed._replace(path=new_path))
                new_headers.append((name, value))
            # Capture only — do NOT call start_response yet.
            # We must defer until after body processing so Content-Length
            # reflects any bytes added by JS injection.
            collected.append((status, new_headers, exc_info))
            # Return a no-op write callable (Flask never uses it)
            return lambda data: None

        body_iter = self.app(environ, capture_start_response)

        if not prefix or not collected:
            # No prefix or headers not captured — pass straight through
            if collected:
                status, hdrs, exc = collected[0]
                start_response(status, hdrs, exc)
            return body_iter

        # Inject a JS interceptor into HTML responses.
        # This patches window.fetch so ALL API calls get the right prefix.
        status, headers, exc_info = collected[0]
        content_type = next((v for k, v in headers if k.lower() == "content-type"), "")

        if "text/html" in content_type:
            body = b"".join(body_iter)
            text = body.decode("utf-8", errors="replace")

            injected = f"""<script>
(function(){{
  var _B = '{prefix}';
  if (!_B) return;
  var _f = window.fetch;
  window.fetch = function(url, opts) {{
    if (typeof url === 'string' && url.charAt(0) === '/' && url.indexOf(_B) !== 0) {{
      url = _B + url;
    }}
    return _f.call(this, url, opts);
  }};
}})();
</script>"""
            # Inject right after <head>, or <body> as fallback
            if "<head>" in text:
                text = text.replace("<head>", "<head>" + injected, 1)
            elif "<body>" in text:
                text = text.replace("<body>", "<body>" + injected, 1)
            else:
                text = injected + text

            encoded = text.encode("utf-8")

            # Build final headers with correct Content-Length BEFORE calling start_response
            final_headers = [
                (k, str(len(encoded)) if k.lower() == "content-length" else v)
                for k, v in headers
            ]
            start_response(status, final_headers, exc_info)
            return [encoded]

        # Non-HTML response — send as-is
        start_response(status, headers, exc_info)
        return body_iter


# ===============================
# SMC GATE (WEBSITE ACCESS)
# ===============================
@app.route("/login", methods=["GET", "POST"])
def terminal_login():
    if request.method == "POST":
        if request.form.get("password") == os.getenv("SITE_PASSWORD"):
            session.permanent = True
            session["terminal_unlocked"] = True
            return redirect("/")
        else:
            print("❌ Invalid SITE_PASSWORD attempt")
    return render_template("login.html")


# ===============================
# LOGOUT
# ===============================
@app.route("/logout")
def logout():
    session.pop("terminal_unlocked", None)
    return redirect("/login")


# ===============================
# MAIN DASHBOARD ROUTE
# ===============================
@app.route("/")
def index():
    if not session.get("terminal_unlocked"):
        return redirect("/login")

    auth = r.hgetall("auth") or {}
    if auth.get("state") == "VALID":
        session["authorized"] = True

    rbus.heartbeat(REDIS_FLASK_HB)
    stats = snapshot()

    return render_template("index.html", **stats)


# ===============================
# BOX ERROR REPORTING
# Called by the frontend _boxGuard when a box crashes.
# Rate-limited: 1 Telegram alert per box per 5 minutes.
# ===============================
@app.route("/core/box-error", methods=["POST"])
def box_error_report():
    from ops.telegram_bot import send as _notify
    data  = request.get_json(silent=True) or {}
    box   = str(data.get("box",   "unknown"))[:50]
    error = str(data.get("error", "no message"))[:300]
    stack = str(data.get("stack", ""))[:400]

    key = f"box_err_alert:{box}"
    if not r.get(key):
        r.setex(key, 300, "1")          # 5-minute cooldown per box
        msg = f"🚨 <b>BOX MALFUNCTION: {box}</b>\n<code>{error}</code>"
        if stack:
            msg += f"\n\n<pre>{stack}</pre>"
        _notify(msg)

    return "", 204


# ===============================
# WSGI APPLICATION
# ===============================
if BASE_PATH:
    application = PrefixMiddleware(app.wsgi_app, BASE_PATH)
else:
    application = app


# ===============================
# ENTRY (dev only)
# ===============================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
