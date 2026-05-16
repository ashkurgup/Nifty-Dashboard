# infra/constants.py
# ==================================================
# PURE CONFIGURATION — NO LOGIC, NO SIDE EFFECTS
# SINGLE SOURCE OF TRUTH
# ==================================================
import os
from dotenv import load_dotenv

load_dotenv()

# MARKET IDENTIFIERS
INDEX_NIFTY = "NIFTY"
INDEX_SENSEX = "SENSEX"
OPTION_CE = "CE"
OPTION_PE = "PE"
INSTR_TYPE_OPT = "OPT"
INSTR_TYPE_FUT = "FUT"

# DEFAULT LOT SIZES
DEFAULT_LOT_NIFTY_OPT = 65
DEFAULT_LOT_SENSEX_OPT = 20
DEFAULT_LOT_NIFTY_FUT = 50
DEFAULT_LOT_SENSEX_FUT = 10

# CHARGES & TAXES (APRIL 2026)
DEFAULT_BROKERAGE = 40.0
GST_RATE = 0.18
STT_RATE = 0.001
STT_RATE_OPTIONS = 0.0015 

# MARKET SESSION (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# NSE TRADING HOLIDAYS — update annually from NSE circular
# Format: "YYYY-MM-DD"
NSE_HOLIDAYS = frozenset({
    # 2025
    "2025-01-26",  # Republic Day
    "2025-02-26",  # Maha Shivaratri
    "2025-03-14",  # Holi
    "2025-04-10",  # Mahavir Jayanti
    "2025-04-14",  # Dr. Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-08-15",  # Independence Day
    "2025-08-27",  # Ganesh Chaturthi
    "2025-10-02",  # Gandhi Jayanti / Dussehra
    "2025-10-20",  # Diwali – Laxmi Puja
    "2025-10-21",  # Diwali – Balipratipada
    "2025-11-05",  # Gurunanak Jayanti
    "2025-12-25",  # Christmas
    # 2026
    "2026-01-26",  # Republic Day
    "2026-02-19",  # Chhatrapati Shivaji Maharaj Jayanti
    "2026-03-04",  # Maha Shivaratri
    "2026-03-25",  # Holi
    "2026-04-02",  # Ram Navami
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-08-15",  # Independence Day
    "2026-08-27",  # Ganesh Chaturthi
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-21",  # Diwali – Laxmi Puja
    "2026-10-22",  # Diwali – Balipratipada
    "2026-11-25",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
})

# THRESHOLDS
VOLUME_EXPANSION_LEVELS = {"WEAK": 1.2, "NORMAL": 1.5, "STRONG": 2.0}
OI_BUILDUP_LEVELS = {"LOW": 0.01, "NORMAL": 0.02, "HIGH": 0.04}
ALERT_COOLDOWN_SECONDS    = 300   # legacy (kept for any direct references)
TELEGRAM_COOLDOWN_SECONDS = 1800  # 30 minutes — same message won't repeat before this

# REDIS KEYS
REDIS_NIFTY_SPOT = "spot:nifty"
REDIS_SENSEX_SPOT = "spot:sensex"
REDIS_TRADES = "active_session_trades"
REDIS_OPT_TICKS = "opt_ticks"
REDIS_LAST_OPT = "last_opt_price"
REDIS_FLASK_HB = "flask:heartbeat"
REDIS_WS_HB = "ws_heartbeat"
REDIS_KITE_HB = "kite_heartbeat"
REDIS_REDIS_HB = "redis_heartbeat"
REDIS_ALERT_QUEUE = "alert_queue"
REDIS_JOB_QUEUE = "job_queue"
REDIS_TRADE_QUEUE = "trade_updates"
REDIS_NOTIFY_QUEUE = "notifications"
TRADE_KEY = "active_session_trades"

# Notion Credentials pulled from your .env
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("DATABASE_ID") # Matches your env key name
