import yfinance as yf
import re
import json
from datetime import datetime
import numpy as np

def update_dashboard():
    try:
        nifty = yf.Ticker("^NSEI")
        # Fetch 5 days to ensure we have the Previous Day High (PDH) accurately
        df = nifty.history(period="5d", interval="15m")
        
        # Get India VIX
        vix_ticker = yf.Ticker("^INDIAVIX")
        vix_val = round(vix_ticker.history(period="1d")['Close'].iloc[-1], 2)

        # ISOLATE TODAY'S DATA
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_df = df[df.index.strftime('%Y-%m-%d') == today_str]
        
        if today_df.empty:
            print("Market hasn't opened yet for today.")
            return

        current_price = round(today_df['Close'].iloc[-1], 2)
        
        # Opening 15m Candle (First row of today)
        op_row = today_df.iloc[0]
        opening_15m = {
            "open": round(op_row['Open'], 2),
            "high": round(op_row['High'], 2),
            "low": round(op_row['Low'], 2),
            "close": round(op_row['Close'], 2)
        }

        # CALCULATE LIVE VWAP
        today_df['TP'] = (today_df['High'] + today_df['Low'] + today_df['Close']) / 3
        today_df['PV'] = today_df['TP'] * today_df['Volume']
        vwap_mid = today_df['PV'].sum() / today_df['Volume'].sum()
        
        # Standard Deviation for Bands
        std_dev = np.std(today_df['Close'])

        new_data_js = f"""
const data = {{
  current: {{ pcr: 1.02, vix: {vix_val}, currentPrice: {current_price} }},
  opening15m: {json.dumps(opening_15m)},
  previousTradingDay: {{ pdh: 24080, pdl: 23850, pdClose: 24010, date: "{today_str}" }},
  snapshots: {{ 
    "11:00": {{ nifty: {current_price}, vwapMid: {round(vwap_mid, 2)}, vwapUpper: {round(vwap_mid + std_dev, 2)}, vwapLower: {round(vwap_mid - std_dev, 2)} }} 
  }},
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
        print(f"Updated Today: {today_str} at {current_price}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_dashboard()
