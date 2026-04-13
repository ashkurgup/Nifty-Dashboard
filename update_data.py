import yfinance as yf
import re
import json
from datetime import datetime
import pytz

def calculate_overlap(df_15m):
    """Counts 15m candle bodies that overlap more than 4 times"""
    overlap_count = 0
    for i in range(1, len(df_15m)):
        c1 = df_15m.iloc[i-1]
        c2 = df_15m.iloc[i]
        # Get body boundaries (ignore wicks)
        c1_min, c1_max = sorted([c1['Open'], c1['Close']])
        c2_min, c2_max = sorted([c2['Open'], c2['Close']])
        # Check if bodies overlap
        if max(c1_min, c2_min) <= min(c1_max, c2_max):
            overlap_count += 1
    return overlap_count

def update_dashboard():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    nifty = yf.Ticker("^NSEI")
    # Fetch today's data (April 13)
    df_5m = nifty.history(period="1d", interval="5m")
    df_15m = nifty.history(period="1d", interval="15m")
    
    # 9:30 - 11:00 Structure Engine Math
    struct_5m = df_5m.between_time('09:30', '11:00')
    struct_15m = df_15m.between_time('09:30', '11:00')
    
    # Biggest Body (9:40 AM logic)
    struct_5m['body_size'] = abs(struct_5m['Close'] - struct_5m['Open'])
    biggest_body = round(struct_5m['body_size'].max(), 2)
    
    # Overlap Calculation (15m candles)
    overlaps = calculate_overlap(struct_15m)

    # Reference Block (Locked after 3:30 PM)
    new_ref = {
        "date": "13-Apr",
        "pdh": round(df_5m['High'].max(), 2),
        "pdl": round(df_5m['Low'].min(), 2),
        "pdc": round(df_5m['Close'].iloc[-1], 2)
    }

    data = {
        "updateTime": now.strftime('%I:%M %p'),
        "current": { "pcr": 1.03, "vix": 20.50, "ltp": new_ref["pdc"] },
        "opening": { "date": "13-Apr", "high": 23892.6, "open": 23619.0, "low": 23556.1, "close": 23842.6 },
        "reference": new_ref,
        "flows": { "date": "10-Apr (Latest)", "fii": 672.09, "dii": 410.05, "fii5d": -1993.85 },
        "structure": { "big": biggest_body, "same": "Yes", "overlap": "Yes" if overlaps > 4 else "No" }
    }

    # Inject into index.html
    with open("index.html", "r") as f:
        content = f.read()
    
    updated_content = re.sub(r"// START_DATA.*?// END_DATA", 
                             f"// START_DATA\nconst data = {json.dumps(data, indent=2)};\n// END_DATA", 
                             content, flags=re.DOTALL)

    with open("index.html", "w") as f:
        f.write(updated_content)

if __name__ == "__main__":
    update_dashboard()
