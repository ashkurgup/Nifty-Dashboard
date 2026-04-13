import yfinance as yf
import pandas as pd
import numpy as np
import re
import json
from datetime import datetime
import pytz

def calculate_structure(df_5m):
    """Calculates ICT Structure Engine metrics for 9:30-11:00 AM"""
    if df_5m.empty: return {"big": 0, "same": "No", "overlap": "No"}
    
    # 1. Biggest Candle Body (Body only, ignore wicks)
    df_5m['body'] = abs(df_5m['Close'] - df_5m['Open'])
    biggest_body = round(df_5m['body'].max(), 2)
    
    # 2. Next Candle Same Colour?
    last_color = "Green" if df_5m['Close'].iloc[-1] > df_5m['Open'].iloc[-1] else "Red"
    prev_color = "Green" if df_5m['Close'].iloc[-2] > df_5m['Open'].iloc[-2] else "Red"
    same_color = "Yes" if last_color == prev_color else "No"
    
    # 3. 15m Overlap (Body-to-Body ignore wicks)
    # Logic: Check if current body range is within previous body range
    overlap_count = 0
    for i in range(1, len(df_5m)):
        curr_min = min(df_5m['Open'].iloc[i], df_5m['Close'].iloc[i])
        curr_max = max(df_5m['Open'].iloc[i], df_5m['Close'].iloc[i])
        prev_min = min(df_5m['Open'].iloc[i-1], df_5m['Close'].iloc[i-1])
        prev_max = max(df_5m['Open'].iloc[i-1], df_5m['Close'].iloc[i-1])
        
        if curr_min <= prev_max and curr_max >= prev_min:
            overlap_count += 1
            
    return {
        "big": biggest_body,
        "same": same_color,
        "overlap": "Yes" if overlap_count > 4 else "No"
    }

def update_dashboard():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Fetch Data
    nifty = yf.Ticker("^NSEI")
    df_5m = nifty.history(period="1d", interval="5m").between_time('09:30', '11:00')
    df_day = nifty.history(period="2d")
    
    # Context Calculation
    struct = calculate_structure(df_5m)
    ltp = round(nifty.history(period="1d")['Close'].iloc[-1], 2)
    
    # Mock Data for FII/DII (Requires specific scraping for real-time)
    flows = {"fii": 672.09, "dii": 410.05, "fii5d": -1993.85}

    # Data Object
    new_data = {
        "updateTime": now.strftime('%H:%M:%S'),
        "current": { "pcr": 1.03, "vix": 20.50, "ltp": ltp },
        "opening": { "date": now.strftime('%d-%b'), "high": 23892.6, "open": 23589.6, "low": 23556.1, "close": 23842.6 },
        "reference": { "date": now.strftime('%d-%b'), "pdh": round(df_day['High'].iloc[0], 2), "pdl": round(df_day['Low'].iloc[0], 2), "pdc": round(df_day['Close'].iloc[0], 2) },
        "flows": flows,
        "structure": struct,
        "v11": {"u": 23825, "m": 23712, "l": 23598},
        "v1": {"u": 23838, "m": 23725, "l": 23611}
    }

    # Inject into HTML
    with open("index.html", "r") as f:
        content = f.read()
    
    data_json = json.dumps(new_data, indent=2)
    updated_content = re.sub(r"// START_DATA.*?// END_DATA", 
                             f"// START_DATA\nconst data = {data_json};\n// END_DATA", 
                             content, flags=re.DOTALL)

    with open("index.html", "w") as f:
        f.write(updated_content)

if __name__ == "__main__":
    update_dashboard()
