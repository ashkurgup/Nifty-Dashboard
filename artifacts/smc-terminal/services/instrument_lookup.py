# services/instrument_lookup.py
import json
import os
import re

# ✅ Ensure absolute path for DigitalOcean environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE_PATH = os.path.join(BASE_DIR, "runtime_data/instruments.json") # Using standard file

_data = None

_file_mtime = None   # track file modification time to auto-reload

def _load():
    global _data, _file_mtime
    if not os.path.exists(FILE_PATH):
        print(f"❌ ERROR: {FILE_PATH} not found")
        _data = []
        return

    mtime = os.path.getmtime(FILE_PATH)
    if _data is not None and mtime == _file_mtime:
        return   # cache is still fresh

    with open(FILE_PATH) as f:
        _data = json.load(f)
    _file_mtime = mtime
    print(f"✅ Loaded {len(_data)} instruments")

def _clean(value):
    return (value or "").strip().replace('"', '').upper()

def get_expiries(index_name):
    _load()
    index_name = _clean(index_name)
    expiries = set()
    for i in _data:
        if i.get("name") == index_name and i.get("instrument_type") in ("CE", "PE"):
            exp = str(i.get("expiry", "")).split("T")[0]
            if exp: expiries.add(exp)
    return sorted(list(expiries))

def get_strikes(index_name, expiry):
    _load()
    index_name, expiry = _clean(index_name), _clean(expiry)
    strikes = set()
    for i in _data:
        if i.get("name") == index_name and str(i.get("expiry", "")).split("T")[0] == expiry:
            symbol = i.get("tradingsymbol", "")
            match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
            if match: strikes.add(int(match.group(1)))
    return sorted(list(strikes))

def find_option(index_name, strike, option_type, expiry):
    _load()
    index_name, option_type, expiry = _clean(index_name), _clean(option_type), _clean(expiry)
    strike = int(strike)
    for i in _data:
        if i.get("name") == index_name and str(i.get("expiry", "")).split("T")[0] == expiry:
            symbol = i.get("tradingsymbol", "")
            if symbol.endswith(option_type):
                match = re.search(r'(\d{4,5})(CE|PE)$', symbol)
                if match and int(match.group(1)) == strike:
                    return {
                        "symbol": symbol,
                        "token": i.get("instrument_token"),
                        "expiry": expiry,
                        "strike": strike
                    }
    return None
