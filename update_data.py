import yfinance as yf
import pandas as pd
import re
import json
import pytz
from datetime import datetime

def update_dashboard():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # 1. Fetch Nifty and VIX
    nifty = yf.Ticker("^NSEI")
    vix_ticker = yf.Ticker("^INDIAVIX")
    
    # Fetch data
    df_5m = nifty.history(period="5d", interval="5m")
    df_15m = nifty.history(period="5d", interval="15m")
    vix_data = vix_ticker.history(period="1d")
    
    if df_5m.empty: 
        print("No data fetched")
        return

    # 2. Identify Today and Yesterday
    days = df_5m.index.normalize().unique()
    today_df = df_5m[df_5m.index.normalize() == days[-1]]
    prev_df = df_5m[df_5m.index.normalize() == days[-2]]
    today_15m = df_15m[df_15m.index.normalize() == days[-1]]

    # 3. Calculate Structure Metrics (Big Candle Logic)
    # Looking for the biggest candle body between 09:30 and 11:00
    struct_df = today_df.between_time('09:30', '11:00').copy()
    big_body, same_color = "--", "--"
    
    if not struct_df.empty:
        struct_df['body'] = abs(struct_df['Close'] - struct_df['Open'])
        big_body = round(struct_df['body'].max(), 2)
        idx_max = struct_df['body'].idxmax()
        try:
            curr_pos = today_df.index.get_loc(idx_max)
            c1_green = today_df.iloc[curr_pos]['Close'] > today_df.iloc[curr_pos]['Open']
            c2_green = today_df.iloc[curr_pos+1]['Close'] > today_df.iloc[curr_pos+1]['Open']
            same_color = "Yes" if c1_green == c2_green else "No"
        except: 
            same_color = "Pending"

    # 4. Reference Levels & Status
    ltp = round(today_df['Close'].iloc[-1], 2)
    pdh = round(prev_df['High'].max(), 2)
    pdl = round(prev_df['Low'].min(), 2)
    pdc = round(prev_df['Close'].iloc[-1], 2)
    odh = round(today_15m['High'].iloc[0], 2) if not today_15m.empty else 0
    
    # Liquidity Logic
    liq_status = "Grab" if (ltp > pdh or ltp < pdl) else "In-Range"

    # 5. Build Final JSON
    data = {
        "updateTime": now.strftime('%I:%M %p'),
        "current": {
            "ltp": ltp, 
            "vix": round(vix_data['Close'].iloc[-1], 2) if not vix_data.empty else "12.5", 
            "pcr": 0.95  # Placeholder: Requires Option Chain API for live
        },
        "opening": {
            "high": odh,
            "low": round(today_15m['Low'].iloc[0], 2) if not today_15m.empty else 0
        },
        "reference": {"pdh": pdh, "pdl": pdl, "pdc": pdc},
        "structure": {"big": big_body, "same": same_color, "overlap": "Yes" if len(today_15m) > 4 else "No"},
        "status": {
            "pdh": "Above" if ltp > pdh else "Below",
            "odh": "Broke" if ltp > odh else "Inside",
            "liq": liq_status,
            "gap11": round(ltp - pdc, 2)
        }
    }

    # Inject into HTML
    try:
        with open("index.html", "r") as f:
            content = f.read()
        updated = re.sub(r"// START_DATA.*?// END_DATA", 
                        f"// START_DATA\nconst data = {json.dumps(data)};\n// END_DATA", 
                        content, flags=re.DOTALL)
        with open("index.html", "w") as f:
            f.write(updated)
        print("Dashboard Updated Successfully")
    except Exception as e:
        print(f"Error updating HTML: {e}")

if __name__ == "__main__":
    update_dashboard()
