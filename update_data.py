import pandas as pd

def calculate_structure_metrics(df_5m, df_daily, live_vix, live_pcr):
    # 1. Reference Levels
    # PDC must be pulled from the daily candle of the previous session
    pdc = df_daily['Close'].iloc[-1] 
    
    # 2. Biggest 5m Body (9:30 - 11:00)
    # Filter for the specific time window
    mask = (df_5m.index.time >= pd.to_datetime('09:30').time()) & \
           (df_5m.index.time <= pd.to_datetime('11:00').time())
    window_df = df_5m.loc[mask].copy()
    
    # Calculate body size: abs(Open - Close)
    window_df['body_size'] = (window_df['Open'] - window_df['Close']).abs()
    
    max_body_row = window_df.loc[window_df['body_size'].idxmax()]
    biggest_body = max_body_row['body_size']
    biggest_body_time = max_body_row.name.strftime('%H:%M')
    
    # 3. Validation Logic for PCR/VIX
    # Ensure these are float types to prevent string concatenation errors
    vix = float(live_vix)
    pcr = float(live_pcr)

    return {
        "PDC": pdc,
        "VIX": vix,
        "PCR": pcr,
        "Biggest_Body": f"{biggest_body:.2f} at {biggest_body_time}",
        "Bias": "BEARISH" if df_5m['Close'].iloc[-1] < pdc else "BULLISH"
    }
