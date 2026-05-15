"""
Persistent auth store — saves the Kite access_token to disk so it survives
Redis flushes and workflow restarts.

On startup the ws_daemon calls try_recover() to reuse the saved token without
running Playwright again if the token is still valid.
"""
import os, json, time
from dotenv import load_dotenv

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH_PATH = os.path.join(BASE_DIR, "runtime_data", "auth.json")

load_dotenv(os.path.join(BASE_DIR, ".env"))


def save_token(token: str):
    """Write token + timestamp to disk atomically."""
    os.makedirs(os.path.dirname(AUTH_PATH), exist_ok=True)
    tmp = AUTH_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"token": token, "saved_at": int(time.time())}, f)
    os.replace(tmp, AUTH_PATH)


def load_token() -> str | None:
    """Return saved token string, or None if file missing."""
    if not os.path.exists(AUTH_PATH):
        return None
    try:
        with open(AUTH_PATH) as f:
            return json.load(f).get("token")
    except Exception:
        return None


def is_valid(token: str) -> bool:
    """Return True if the token still works against the Kite API."""
    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=os.getenv("API_KEY"))
        kite.set_access_token(token)
        kite.profile()
        return True
    except Exception:
        return False


def try_recover(r, AUTH_KEY: str) -> bool:
    """
    Load token from disk, validate it, and if good push it into Redis as VALID.
    Returns True if recovery succeeded (Playwright not needed).
    """
    token = load_token()
    if not token:
        print("💾 No saved token on disk")
        return False
    print("💾 Saved token found — validating…")
    if is_valid(token):
        r.hset(AUTH_KEY, mapping={
            "state":      "VALID",
            "token":      token,
            "updated_at": int(time.time()),
        })
        print("✅ Recovered valid token from disk — Playwright not needed")
        return True
    print("💾 Saved token is expired — will run Playwright")
    return False
