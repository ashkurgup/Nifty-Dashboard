import os
import re
import redis
from flask import Flask, render_template, session, redirect, request, g
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BASE_PATH = os.getenv("BASE_PATH", "").rstrip("/")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", os.getenv("SITE_PASSWORD", "dev-secret"))

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

# ===============================
# BLUEPRINTS
# ===============================
app.register_blueprint(auth_gateway_blueprint, url_prefix="/core")
app.register_blueprint(terminal_core_blueprint, url_prefix="/core")
app.register_blueprint(quick_trade_blueprint, url_prefix="/core")

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
                    path = parsed.path
                    # Add prefix if path doesn't already have it
                    if path.startswith("/") and not path.startswith(prefix + "/") and path != prefix:
                        new_path = prefix + path
                        value = urlunparse(parsed._replace(path=new_path))
                new_headers.append((name, value))
            collected.append((status, new_headers))
            return start_response(status, new_headers, exc_info)

        body_iter = self.app(environ, capture_start_response)

        if not prefix:
            return body_iter

        # Inject a JS interceptor into HTML responses.
        # This patches window.fetch and window.location so ALL API calls
        # (string literals, template literals, dynamic URLs) get the right prefix.
        if collected:
            status, headers = collected[0]
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
                # Inject right after <head> or at the top of <body>
                if "<head>" in text:
                    text = text.replace("<head>", "<head>" + injected, 1)
                elif "<body>" in text:
                    text = text.replace("<body>", "<body>" + injected, 1)
                else:
                    text = injected + text
                encoded = text.encode("utf-8")
                # Update Content-Length
                new_headers = [(k, str(len(encoded)) if k.lower() == "content-length" else v)
                               for k, v in headers]
                return [encoded]

        return body_iter


# ===============================
# SMC GATE (WEBSITE ACCESS)
# ===============================
@app.route("/login", methods=["GET", "POST"])
def terminal_login():
    if request.method == "POST":
        if request.form.get("password") == os.getenv("SITE_PASSWORD"):
            session["terminal_unlocked"] = True
            return redirect("/")
        else:
            print("❌ Invalid SITE_PASSWORD attempt")
    return render_template("login.html")


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
