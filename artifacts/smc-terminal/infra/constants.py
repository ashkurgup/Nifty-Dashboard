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
