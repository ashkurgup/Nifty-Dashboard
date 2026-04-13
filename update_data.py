import yfinance as yf
import pandas as pd
import json
from datetime import datetime, time
import pytz

IST = pytz.timezone('Asia/Kolkata')

def run_engine():
    now = datetime.now(IST)
    today = now.date()
    
    # Exit if not a trading day
    if now.weekday() >= 5: return

    # --- DATA FETCHING ---
    df_1m = yf.download("^NSEI", period="1d", interval="1m")
    df_5m = yf.download("^NSEI", period="1d", interval="5m")
    
    # --- BLOCK: REFERENCE LEVELS & INSTITUTION (3:45 PM PIVOT) ---
    ref_trigger = time(15, 45)
    is_after_market = now.time() >= ref_trigger
    hist_daily = yf.download("^NSEI", period="5d", interval="1d")
    ref_row = hist_daily.iloc[-1] if is_after_market else hist_daily.iloc[-2]
    
    # --- BLOCK: OPENING RANGE (15M) ---
    or_data = {"high": "--", "open": "--", "close": "--", "low": "--"}
    if now.time() >= time(9, 31):
        or_15 = df_1m.between_time('09:15', '09:30')
        if not or_15.empty:
            or_data = {
                "high": round(or_15['High'].max(), 2),
                "open": round(or_15.iloc[0]['Open'], 2),
                "close": round(or_15.iloc[-1]['Close'], 2),
                "low": round(or_15.iloc[-1]['Low'], 2)
            }

    # --- BLOCK: STRUCTURE ENGINE ---
    morning_5m = df_5m.between_time('09:30', '11:00')
    biggest_body = round(abs(morning_5m['Open'] - morning_5m['Close']).max(), 2) if not morning_5m.empty else "--"

    # --- BLOCK: VWAP ANCHORS ---
    def calc_vwap(df):
        return round(((df['High'] + df['Low'] + df['Close'])/3 * df['Volume']).sum() / df['Volume'].sum(), 2) if not df.empty else "--"
    
    vwap_11 = calc_vwap(df_1m.between_time('11:00', '15:30'))
    vwap_1 = calc_vwap(df_1m.between_time('13:00', '15:30'))

    # --- FINAL CONSOLIDATED OUTPUT ---
    master_output = {
        "meta": {"updated": now.strftime("%I:%M %p"), "val": round(df_1m['Close'].iloc[-1], 2), "pcr": 0.95, "vix": 14.2, "bias": "BEARISH"},
        "opening_range": or_data,
        "reference": {"pdh": round(ref_row['High'], 2), "pdl": round(ref_row['Low'], 2), "pdc": round(ref_row['Close'], 2)},
        "institution": {"status": "Updated" if is_after_market else "Awaiting Today's Data", "fii": "--", "dii": "--"},
        "structure": {"biggest_body": biggest_body},
        "vwap11": vwap_11,
        "vwap1": vwap_1
    }

    with open('market_data.json', 'w') as f:
        json.dump(master_output, f, indent=4)

if __name__ == "__main__":
    run_engine()
