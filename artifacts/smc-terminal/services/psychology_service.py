import time
import json
import redis
from datetime import datetime
from ops.telegram_bot import send as notify
from infra.constants import TRADE_KEY, TELEGRAM_COOLDOWN_SECONDS
from services.trading_calendar import get_trading_date

r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

def check_psychology_triggers():
    """Monitors SL/TG breaches, Duration, and Daily PnL for discipline."""
    raw_trades = r.get(TRADE_KEY)
    trades = json.loads(raw_trades) if raw_trades else []
    today = get_trading_date()
    
    daily_pnl = 0
    
    for t in trades:
        if t.get('date') != today: continue
        
        daily_pnl += t.get('net_pnl', 0)
        
        if t.get('status') == "ACTIVE":
            ltp = float(r.get(f"ltp:{t['token']}") or 0)
            sl = float(t.get('sl', 0))
            tg = float(t.get('tg', 0))
            
            # 1. SL/TG Breach — once fired, silent for 30 hours
            side = t.get('direction', 'LONG')
            is_breached = False
            if side == "LONG"  and (ltp <= sl or ltp >= tg): is_breached = True
            if side == "SHORT" and (ltp >= sl or ltp <= tg): is_breached = True
            
            breach_key = f"psych_breach:{t['id']}"
            if is_breached and not r.get(breach_key):
                notify(f"🧨 <b>ACTION REQUIRED: {t['symbol']}</b>\nLTP ({ltp}) has hit your plan ({sl}/{tg}).\n"
                       f"Don't lie to yourself. Don't move the SL. Close the position and breathe.")
                r.set(breach_key, "1", ex=TELEGRAM_COOLDOWN_SECONDS)

            # 2. Duration Discipline — once fired per trade, silent for 30 hours
            elapsed   = (time.time() - t.get('created_at', time.time())) / 60
            last_alert = float(r.get(f"psych_dur:{t['id']}") or 0)
            
            if elapsed >= 90 and last_alert == 0:
                notify(f"⏳ <b>YOU ARE STUCK: {t['symbol']}</b>\n90 minutes passed. Is this a trade or a relationship? "
                       f"Market dynamics have changed. Re-evaluate or exit.")
                r.set(f"psych_dur:{t['id']}", 90, ex=TELEGRAM_COOLDOWN_SECONDS)
            elif elapsed >= (last_alert + 60) and last_alert >= 90:
                notify(f"💀 <b>ZOMBIE TRADE: {t['symbol']}</b>\nAnother hour gone. Your capital is dying in a sideways move. Cut it.")
                r.set(f"psych_dur:{t['id']}", elapsed, ex=TELEGRAM_COOLDOWN_SECONDS)

    _process_pnl_milestones(daily_pnl)

def _process_pnl_milestones(pnl):
    # Daily Loss Limit (₹2200) — 30-hour lock
    if pnl <= -2200 and not r.get("lock_loss_2200"):
        notify("🛑 <b>STOP. WALK AWAY.</b>\nDaily loss hit ₹2200. It is not your day. You have done this before and lost 70% of the time trying to 'recover'. "
               "Save your precious capital. Live to fight tomorrow.")
        r.set("lock_loss_2200", "1", ex=TELEGRAM_COOLDOWN_SECONDS)

    # Profit Milestones — 30-hour lock each
    elif pnl >= 8000 and not r.get("lock_win_8000"):
        notify("👑 <b>90% TREND CAPTURED.</b>\n₹8000 profit. You have won today. Wait for a deep pullback or switch to GTT orders. "
               "Don't give this back to the market by chasing.")
        r.set("lock_win_8000", "1", ex=TELEGRAM_COOLDOWN_SECONDS)
    elif pnl >= 6500 and not r.get("lock_win_6500"):
        notify("🎯 <b>90% TREND REACHED.</b>\n₹6500 in the bag. Think about GTT orders now. Following the price will lead to overtrading.")
        r.set("lock_win_6500", "1", ex=TELEGRAM_COOLDOWN_SECONDS)
    elif pnl >= 4500 and not r.get("lock_win_4500"):
        notify("💰 <b>80% TREND REACHED.</b>\nYou achieved what the market gives only 80% of the time. Is it worth risking this for more?")
        r.set("lock_win_4500", "1", ex=TELEGRAM_COOLDOWN_SECONDS)

def send_eod_summary():
    raw_trades = r.get(TRADE_KEY)
    trades = json.loads(raw_trades) if raw_trades else []
    today = get_trading_date()
    today_trades = [t for t in trades if t.get('date') == today]
    
    if not today_trades: return

    total_pnl = sum(t.get('net_pnl', 0) for t in today_trades)
    pnls = [t.get('net_pnl', 0) for t in today_trades]
    
    summary = (
        f"<b>📊 EOD SUMMARY | {today}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Total Trades: {len(today_trades)}\n"
        f"Net PnL: <b>₹{round(total_pnl, 2)}</b>\n"
        f"Biggest Win: ₹{max(pnls) if pnls else 0}\n"
        f"Biggest Loss: ₹{min(pnls) if pnls else 0}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{'Great execution.' if total_pnl > 0 else 'Review the journal. No revenge tomorrow.'}"
    )
    notify(summary)
