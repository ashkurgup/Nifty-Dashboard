# engine.py

import os
import json
from typing import Dict, Optional

from infra.constants import *

# ===============================
# INTERNAL STATE
# ===============================
_ENGINE_READY = False
_INSTRUMENT_CACHE: Dict[str, dict] = {}
_LOT_CACHE: Dict[str, int] = {}


# ===============================
# INIT
# ===============================
def init(config: Optional[dict] = None) -> None:
    global _ENGINE_READY
    if _ENGINE_READY:
        return

    load_instrument_cache()
    _ENGINE_READY = True


# ===============================
# INSTRUMENT CACHE
# ===============================
def load_instrument_cache() -> None:
    global _INSTRUMENT_CACHE, _LOT_CACHE

    path = "runtime_data/instruments.json"

    if not os.path.exists(path):
        print("⚠ instruments.json not found")
        return

    try:
        with open(path, "r") as f:
            instruments = json.load(f)

        for inst in instruments:
            key = _instrument_key(inst)
            token = str(inst.get("instrument_token"))

            _INSTRUMENT_CACHE[key] = inst
            _LOT_CACHE[token] = int(inst.get("lot_size", 1))

        print(f"✅ Loaded {len(_INSTRUMENT_CACHE)} instruments into cache.")

    except Exception as e:
        print(f"[ENGINE LOAD ERROR] {e}")


def _instrument_key(i: dict) -> str:
    try:
        if i.get("type") == INSTR_TYPE_FUT:
            return f"{i['name']}_FUT_{i['expiry']}"
        return f"{i['name']}_{i['strike']}_{i['instrument_type']}_{i['expiry']}"
    except Exception:
        return "INVALID_KEY"


# ===============================
# LOT SIZE HELPER (READ ONLY)
# ===============================
def get_lot_size(token: str) -> int:
    return _LOT_CACHE.get(str(token), DEFAULT_LOT_NIFTY_OPT)

