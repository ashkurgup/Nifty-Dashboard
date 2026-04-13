import yfinance as yf
import pandas as pd
import re, json, pytz
from datetime import datetime

def update_dashboard():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    nifty = yf.Ticker("^NSEI")
    
    # Fetch Data
    df_5m = nifty.history(period="2d", interval="5m")
    df_15m = nifty.history(period="2d", interval="15m")
    
    if len(df_5m) < 5: return

    # Extract Today's Data
    today_str = now.strftime('%Y-%m-%d')
    df_today = df_5m.loc[today_str]
    df_15_today = df_15m.loc[today_str]
    
    # Structure Logic (9:30 - 11:00)
    struct_df = df_today.between_time('09:30', '11:00').copy()
    big_body = 0
    same_color = "N/A"
    
    if not struct_df.empty:
        struct_df['body_size'] = abs(struct_df['Close'] - struct_df['Open'])
        idx_max = struct_df['body_size'].idxmax()
        big_body = round(struct_df['body_size'].max(), 2)
        
        # Check if next candle is same color
        try:
            current_pos = df_today.index.get_loc(idx_max)
            curr_green = df_today.iloc[current_pos]['Close'] > df_today.iloc[current_pos]['Open']
            next_green = df_today.iloc[current_pos+1]['Close'] > df_today.iloc[current_pos+1]['Open']
            same_color = "Yes" if curr_green == next_green else "No"
        except: same_color = "Wait..."

    # Reference Levels (Yesterday)
    prev_day = df_5m.index.unique().date[-2]
    df_prev = df_5m.loc[prev_day.strftime('%Y-%m-%d')]
    
    data = {
        "updateTime": now.strftime('%I:%M %p'),
        "current": {"ltp": round(df_today['Close'].iloc[-1], 2), "vix": 14.2, "pcr": 0.95},
        "opening": {
            "high": round(df_15_today['High'].iloc[0], 2),
            "low": round(df_15_today['Low'].iloc[0], 2),
            "open": round(df_15_today['Open'].iloc[0], 2),
            "close": round(df_15_today['Close'].iloc[0], 2)
        },
        "reference": {
            "pdh": round(df_prev['High'].max(), 2),
            "pdl": round(df_prev['Low'].min(), 2),
            "pdc": round(df_prev['Close'].iloc[-1], 2)
        },
        "structure": {
            "big": big_body,
            "same": same_color,
            "overlap": "Calculating..." 
        },
        "v11": {"u": 24150, "m": 24100, "l": 24050},
        "v1": {"u": 24200, "m": 24150, "l": 24100}
    }

    # Inject into HTML
    with open("index.html", "r") as f:
        content = f.read()
    updated = re.sub(r"// START_DATA.*?// END_DATA", f"// START_DATA\nconst data = {json.dumps(data)};\n// END_DATA", content, flags=re.DOTALL)
    with open("index.html", "w") as f:
        f.write(updated)

if __name__ == "__main__":
    update_dashboard()
