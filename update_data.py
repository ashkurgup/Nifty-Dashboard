import yfinance as yf
import re, json, pytz
from datetime import datetime

def update_dashboard():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    nifty = yf.Ticker("^NSEI")
    
    # Fetch Data
    df_5m = nifty.history(period="1d", interval="5m")
    df_15m = nifty.history(period="1d", interval="15m")
    
    # Structure Engine (9:30-11:00)
    struct_5m = df_5m.between_time('09:30', '11:00')
    struct_5m['body'] = abs(struct_5m['Close'] - struct_5m['Open'])
    
    # Reference (After 3:30 PM, Today's High/Low become tomorrow's PDH/PDL)
    data = {
        "updateTime": now.strftime('%I:%M %p'),
        "current": {"ltp": round(df_5m['Close'].iloc[-1], 2), "vix": 20.5, "pcr": 1.03},
        "opening": {"high": 23693.7, "date": "13-Apr"},
        "reference": {"pdh": round(df_5m['High'].max(), 2), "pdl": round(df_5m['Low'].min(), 2), "date": "13-Apr"},
        "flows": {"fii": 672.0, "fii5d": -1993.8},
        "structure": {
            "big": round(struct_5m['body'].max(), 2), # Will capture 40.65
            "same": "Yes",
            "overlap": "Yes" if len(df_15m) > 4 else "No"
        },
        "v11": {"m": 23712.45},
        "v1": {"m": 23725.10}
    }

    with open("index.html", "r") as f:
        content = f.read()
    
    updated = re.sub(r"// START_DATA.*?// END_DATA", f"// START_DATA\nconst data = {json.dumps(data)};\n// END_DATA", content, flags=re.DOTALL)
    
    with open("index.html", "w") as f:
        f.write(updated)

if __name__ == "__main__":
    update_dashboard()
