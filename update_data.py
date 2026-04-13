import yfinance as yf
import re
import json

def update_dashboard():
    try:
        # 1. Fetch Nifty 50 Data
        nifty = yf.Ticker("^NSEI")
        df = nifty.history(period="5d", interval="15m")
        
        if df.empty:
            print("No data found")
            return

        current_price = round(df['Close'].iloc[-1], 2)
        # Getting the first 15m candle of the current/most recent day
        opening_15m = {
            "open": round(df['Open'].iloc[0], 2),
            "high": round(df['High'].iloc[0], 2),
            "low": round(df['Low'].iloc[0], 2),
            "close": round(df['Close'].iloc[0], 2)
        }

        # 2. Format the new data block exactly for your JS
        new_data_js = f"""
const data = {{
  current: {{ pcr: 1.05, vix: 14.2, currentPrice: {current_price} }},
  opening15m: {json.dumps(opening_15m)},
  previousTradingDay: {{ pdh: {opening_15m['high']}, pdl: {opening_15m['low']}, pdClose: {opening_15m['close']}, date: "Live Update" }},
  snapshots: {{ "11:00": {{}}, "13:30": {{}} }},
  structureCandles930to1100: []
}};
"""
        # 3. Read index.html and swap
        with open("index.html", "r") as f:
            content = f.read()

        updated_content = re.sub(r"// START_DATA.*?// END_DATA", 
                                 f"// START_DATA{new_data_js}// END_DATA", 
                                 content, flags=re.DOTALL)

        with open("index.html", "w") as f:
            f.write(updated_content)
            
        print(f"Success! Updated price to {current_price}")

    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    update_dashboard()
