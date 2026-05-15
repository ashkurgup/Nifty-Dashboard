"""
ROLE: Session freshness
"""

from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")


def is_session_fresh(auth: dict) -> bool:
    try:
        updated = int(auth.get("updated_at") or 0)

        now = datetime.now(IST)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        return updated >= int(today_start.timestamp())

    except:
        return False
