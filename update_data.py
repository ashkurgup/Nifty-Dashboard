import yfinance as yf
import re

def update_dashboard():
    # 1. Fetch Nifty 50 Data from Yahoo Finance
    nifty = yf.Ticker("^NSEI")
    # Get last 2 days of 15m candles
    df = nifty.history(period="2d", interval="15m")
    
    current_price = round(df['Close'].iloc[-1], 2)
    opening_15m = {
        "open": round(df['Open'].iloc[0], 2),
        "high": round(df['High'].iloc[0], 2),
        "low": round(df['Low'].iloc[0], 2),
        "close": round(df['Close'].iloc[0], 2)
    }

    # 2. Format the new data block
    new_data_js = f"""
const data = {{
  current: {{ pcr: 1.0, vix: 14.0, currentPrice: {current_price} }},
  opening15m: {opening_15m},
  previousTradingDay: {{ pdh: {opening_15m['high']}, pdl: {opening_15m['low']}, pdClose: {opening_15m['close']}, date: "Live Update" }},
  snapshots: {{ "11:00": {{}}, "13:30": {{}} }},
  structureCandles930to1100: []
}};
"""
    # 3. Read index.html and swap the data
    with open("index.html", "r") as f:
        content = f.read()

    # Regular expression to find text between START_DATA and END_DATA
    updated_content = re.sub(r"// START_DATA.*?// END_DATA", 
                             f"// START_DATA{new_data_js}// END_DATA", 
                             content, flags=re.DOTALL)

    with open("index.html", "w") as f:
        f.write(updated_content)

if __name__ == "__main__":
    update_dashboard()
