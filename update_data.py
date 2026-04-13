import yfinance as yf
import re
import json
import numpy as np

def update_dashboard():
    try:
        # 1. Fetch Nifty 50 with 15m intervals for today
        nifty = yf.Ticker("^NSEI")
        df = nifty.history(period="1d", interval="15m")
        vix_ticker = yf.Ticker("^INDIAVIX")
        vix_val = round(vix_ticker.history(period="1d")['Close'].iloc[-1], 2)

        if df.empty: return print("Market closed.")

        # 2. Precise VWAP & Band Math
        df['TP'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['PV'] = df['TP'] * df['Volume']
        
        vwap_mid = df['PV'].sum() / df['Volume'].sum()
        
        # Calculate Volume Weighted Standard Deviation for the Bands
        # This fixes the "looks wrong" issue
        weighted_var = np.average((df['TP'] - vwap_mid)**2, weights=df['Volume'])
        std_dev = np.sqrt(weighted_var)

        current_price = round(df['Close'].iloc[-1], 2)
        opening_15m = {
            "open": round(df['Open'].iloc[0], 2),
            "high": round(df['High'].iloc[0], 2),
            "low": round(df['Low'].iloc[0], 2),
            "close": round(df['Close'].iloc[0], 2)
        }

        # 3. Final Data Injection
        new_data_js = f"""
const data = {{
  current: {{ pcr: 1.02, vix: {vix_val}, currentPrice: {current_price} }},
  opening15m: {json.dumps(opening_15m)},
  previousTradingDay: {{ pdh: 24080, pdl: 23850, pdClose: 24010, date: "April 13, 2026" }},
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
        print("Success: Live Data Updated")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_dashboard()
