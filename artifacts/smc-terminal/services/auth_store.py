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


def save_token(token: str, login_at: int | None = None):
    """Write token + original login timestamp to disk atomically."""
    os.makedirs(os.path.dirname(AUTH_PATH), exist_ok=True)
    tmp = AUTH_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump({
            "token":    token,
            "login_at": login_at or int(time.time()),  # when Kite session was created
            "saved_at": int(time.time()),
        }, f)
    os.replace(tmp, AUTH_PATH)


def load_auth() -> dict | None:
    """Return saved auth dict {token, login_at, saved_at}, or None if missing."""
    if not os.path.exists(AUTH_PATH):
        return None
    try:
        with open(AUTH_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def load_token() -> str | None:
    """Return saved token string, or None if file missing."""
    d = load_auth()
    return d.get("token") if d else None


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
    Preserves the original login_at so LAST KITE shows the real login time,
    not the restart/recovery time.
    Returns True if recovery succeeded (Playwright not needed).
    """
    saved = load_auth()
    if not saved or not saved.get("token"):
        print("💾 No saved token on disk")
        return False
    print("💾 Saved token found — validating…")
    if is_valid(saved["token"]):
        r.hset(AUTH_KEY, mapping={
            "state":      "VALID",
            "token":      saved["token"],
            "updated_at": saved.get("login_at", int(time.time())),  # original login time
        })
        print("✅ Recovered valid token from disk — Playwright not needed")
        return True
    print("💾 Saved token is expired — will run Playwright")
    return False
