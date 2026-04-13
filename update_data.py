import yfinance as yf
import pandas as pd
import numpy as np
import re
import json
from datetime import datetime
import pytz

def get_ist_time():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

def fetch_fii_dii():
    # Note: Real-time FII/DII data is released after 6:30 PM. 
    # This fetches the latest available reported values.
    # In a professional setup, you'd scrape a site like Moneycontrol/NSE.
    # Here we use dummy logic that you can replace with a scraper.
    return {"fii": -1240.50, "dii": 980.20, "fii5d": -4550.00}

def calculate_vwap_bands(df):
    if df.empty:
        return {"u": 0, "m": 0, "l": 0}
    
    df['TP'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['PV'] = df['TP'] * df['Volume']
    
    cum_vol = df['Volume'].sum()
    if cum_vol == 0: return {"u": 0, "m": 0, "l": 0}
    
    vwap_mid = df['PV'].sum() / cum_vol
    std_dev = np.std(df['Close'])
    
    return {
        "m": round(vwap_mid, 2),
        "u": round(vwap_mid + (std_dev * 1.5), 2),
        "l": round(vwap_mid - (std_dev * 1.5), 2)
    }

def update_dashboard():
    now = get_ist_time()
    current_hour_min = now.hour * 100 + now.minute
    today_str = now.strftime('%d-%b-%Y')

    # 1. Fetch Nifty Data
    nifty = yf.Ticker("^NSEI")
    vix_ticker = yf.Ticker("^INDIAVIX")
    
    # 2. Reset Logic (9:00 AM Reset)
    is_reset_time = current_hour_min < 915
    
    # 3. Opening Range Logic (Trigger @ 9:31 AM)
    is_opening_ready = current_hour_min >= 931
    
    # 4. Fetch Market Data
    hist_15m = nifty.history(period="1d", interval="15m")
    vix_val = round(vix_ticker.history(period="1d")['Close'].iloc[-1], 2)
    ltp = round(hist_15m['Close'].iloc[-1], 2)

    # Opening Range Capture
    if is_opening_ready and not hist_15m.empty:
        op = hist_15m.iloc[0]
        opening_data = {
            "date": today_str,
            "high": round(op['High'], 2),
            "open": round(op['Open'], 2),
            "close": round(op['Close'], 2),
            "low": round(op['Low'], 2)
        }
    else:
        opening_data = {"date": today_str, "high": 0, "open": 0, "close": 0, "low": 0}

    # VWAP Snapshots
    v11_data = {"u": 0, "m": 0, "l": 0}
    v1_data = {"u": 0, "m": 0, "l": 0}
    
    if current_hour_min >= 1100:
        v11_df = hist_15m.between_time('09:15', '11:00')
        v11_data = calculate_vwap_bands(v11_df)
    
    if current_hour_min >= 1330:
        v1_df = hist_15m.between_time('09:15', '13:30')
        v1_data = calculate_vwap_bands(v1_df)

    # Reference Block (Trigger @ 3:31 PM)
    flows = fetch_fii_dii()
    # If before 3:30, use yesterday's PDC/PDH/PDL
    # If after 3:31, you'd calculate today's High/Low as the new Reference
    ref_data = {
        "date": "13-Apr", # Placeholder for manual/scrape date
        "pdh": 24080, 
        "pdl": 23850, 
        "pdc": 24010
    }

    # Construct the JSON Data
    new_data = {
        "updateTime": now.strftime('%H:%M:%S'),
        "current": { "pcr": 1.05, "vix": vix_val, "ltp": ltp },
        "opening": opening_data,
        "reference": ref_data,
        "flows": flows,
        "v11": v11_data,
        "v1": v1_data,
        "structure": { "big": 22, "same": "Yes", "overlap": "Yes" }
    }

    # 5. Write to index.html
    new_data_js = f"const data = {json.dumps(new_data, indent=2)};"
    
    with open("index.html", "r") as f:
        content = f.read()

    updated_content = re.sub(r"// START_DATA.*?// END_DATA", 
                             f"// START_DATA\n{new_data_js}\n// END_DATA", 
                             content, flags=re.DOTALL)

    with open("index.html", "w") as f:
        f.write(updated_content)

if __name__ == "__main__":
    update_dashboard()
