import requests
import os
from datetime import datetime
from infra.constants import NOTION_TOKEN, NOTION_DB_ID

def log_trade_to_notion(trade_data):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # Calculate Duration (in minutes)
    duration = 0
    try:
        fmt = "%H:%M:%S"
        t1 = datetime.strptime(trade_data.get('entry_time', '00:00:00'), fmt)
        t2 = datetime.strptime(trade_data.get('exit_time', '00:00:00'), fmt)
        duration = int((t2 - t1).total_seconds() / 60)
    except:
        duration = 0

    # Win/Lose Logic for Status
    pnl_value = float(trade_data.get('net_pnl', 0))
    win_loss_status = "Win" if pnl_value > 0 else "Lose" if pnl_value < 0 else "Breakeven"

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            # --- From image_85da91.png ---
            "Month": {"title": [{"text": {"content": trade_data.get('month', "May'26")}}]},
            "Trade Id": {"rich_text": [{"text": {"content": str(trade_data.get('id', ''))}}]},
            "Date": {"date": {"start": str(trade_data.get('date', ''))}},
            "Entry Time": {"rich_text": [{"text": {"content": str(trade_data.get('entry_time', '--'))}}]},
            "Duration": {"number": duration}, 
            "Index": {"select": {"name": str(trade_data.get('index', 'SENSEX'))}},
            "Direction": {"select": {"name": str(trade_data.get('direction', 'Long'))}},
            "Symbol": {"rich_text": [{"text": {"content": str(trade_data.get('symbol', ''))}}]},
            "Multiplier": {"number": int(trade_data.get('multiplier', 20))},
            "Lots": {"number": int(trade_data.get('lots', 1))},
            "Entry Price": {"number": float(trade_data.get('entryPrice', 0))},
            "Exit Price": {"number": float(trade_data.get('exit_price', 0))},
            "Status": {"select": {"name": win_loss_status}},

            # --- From image_85dab2.png ---
            "Setup": {"select": {"name": str(trade_data.get('setup', 'SMC Setup'))}},
            "SL": {"number": float(trade_data.get('sl', 100))}, # Ensure 'sl' is in your trade dict
            "TG": {"number": float(trade_data.get('tg', 250))}, # Ensure 'tg' is in your trade dict
            "PnL": {"number": pnl_value},
            "MAE": {"number": float(trade_data.get('mae', 0))},
            "MFE": {"number": float(trade_data.get('mfe', 0))},
            "Entry Emotion": {"select": {"name": str(trade_data.get('entry_emotion', 'Calm'))}},
            "Exit Emotion": {"select": {"name": str(trade_data.get('exit_emotion', 'Disciplined'))}},
            "Brokerage": {"number": float(trade_data.get('brokerage', 0))}
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"✅ Notion Updated: {trade_data.get('id')} ({win_loss_status})")
        else:
            print(f"❌ Notion Error: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False
