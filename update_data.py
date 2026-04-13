import yfinance as yf
import re
import json
from datetime import datetime

def update_dashboard():
    try:
        # Fetch Nifty 50
        nifty = yf.Ticker("^NSEI")
        
        # Get 1-minute data for the last 2 days to find the current 'Live' price
        df = nifty.history(period="2d", interval="1m")
        
        if df.empty:
            print("Market closed or no data available.")
            return

        current_price = round(df['Close'].iloc[-1], 2)

        # Get the Opening Range (9:15 AM IST)
        # We look at today's data specifically
        today_date = datetime.now().strftime('%Y-%m-%d')
        today_data = df[df.index.strftime('%Y-%m-%d') == today_date]

        if not today_data.empty:
            # If today has started, take the first 15 mins (first 15 rows of 1m data)
            opening_range = today_data.iloc[:15]
            opening_15m = {
                "open": round(opening_range['Open'].iloc[0], 2),
                "high": round(opening_range['High'].max(), 2),
                "low": round(opening_range['Low'].min(), 2),
                "close": round(opening_range['Close'].iloc[-1], 2)
            }
            ref_label = "Today's Open"
        else:
            # If today hasn't started yet, show yesterday as reference
            opening_15m = {"open": 0, "high": 0, "low": 0, "close": 0}
            ref_label = "Waiting for 9:15 AM..."

        # Format JavaScript Block
        new_data_js = f"""
const data = {{
  current: {{ pcr: 1.05, vix: 14.2, currentPrice: {current_price} }},
  opening15m: {json.dumps(opening_15m)},
  previousTradingDay: {{ pdh: {opening_15m['high']}, pdl: {opening_15m['low']}, pdClose: {opening_15m['close']}, date: "{ref_label}" }},
  snapshots: {{ "11:00": {{}}, "13:30": {{}} }},
  structureCandles930to1100: []
}};
"""
        with open("index.html", "r") as f:
            content = f.read()

        updated_content = re.sub(r"// START_DATA.*?// END_DATA", 
                                 f"// START_DATA{new_data_js}// END_DATA", 
                                 content, flags=re.DOTALL)

        with open("index.html", "w") as f:
            f.write(updated_content)
            
        print(f"Update Success: {current_price}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_dashboard()
