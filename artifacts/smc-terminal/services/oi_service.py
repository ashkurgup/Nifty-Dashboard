"""
OI Snapshot Service — Nifty weekly options OI analysis.

Finds nearest weekly expiry, fetches OI for CE/PE strikes LTP±500 step 50.
Computes: max_pain (max total OI strike), ce_wall (highest CE OI above LTP),
pe_wall (highest PE OI below LTP), trend vs previous snapshot.

Redis keys:
  OI_SNAP      — current snapshot (no TTL, always overwritten)
  OI_PREV_SNAP — previous snapshot, TTL 7200 s
"""
import os
import json
import redis
import pytz
from datetime import datetime, date

_r   = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
_IST = pytz.timezone("Asia/Kolkata")

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTR_FILE = os.path.join(BASE_DIR, "runtime_data", "instruments.json")


def _kite():
    auth = _r.hgetall("auth") or {}
    if auth.get("state") != "VALID" or not auth.get("token"):
        return None
    from kiteconnect import KiteConnect
    k = KiteConnect(api_key=os.getenv("API_KEY"))
    k.set_access_token(auth["token"])
    return k


def _load_instruments():
    try:
        with open(INSTR_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _null_response():
    snap_raw = _r.get("OI_SNAP")
    if snap_raw:
        try:
            snap = json.loads(snap_raw)
            return {
                "max_pain":                   snap.get("max_pain"),
                "ce_wall":                    snap.get("ce_wall"),
                "ce_trend":                   "--",
                "pe_wall":                    snap.get("pe_wall"),
                "pe_trend":                   "--",
                "last_fetch":                 snap.get("timestamp", "pending"),
                "ltp_distance_from_max_pain": snap.get("ltp_distance_from_max_pain"),
            }
        except Exception:
            pass
    return {
        "max_pain": None, "ce_wall": None, "pe_wall": None,
        "ce_trend": "--", "pe_trend": "--", "last_fetch": "pending",
        "ltp_distance_from_max_pain": None,
    }


def get_oi_snapshot() -> dict:
    kite = _kite()
    if kite is None:
        return _null_response()

    try:
        ltp_raw = _r.get("ltp:256265")
        if ltp_raw:
            ltp = float(ltp_raw)
        else:
            stats_raw = _r.get("NIFTY_STATS")
            ltp = json.loads(stats_raw).get("lp", 0) if stats_raw else 0

        if not ltp:
            return _null_response()

        instruments = _load_instruments()
        if not instruments:
            return _null_response()

        nifty_opts = [
            i for i in instruments
            if i.get("name") == "NIFTY"
            and i.get("instrument_type") in ("CE", "PE")
            and str(i.get("expiry", "")).split("T")[0] >= date.today().isoformat()
        ]

        if not nifty_opts:
            return _null_response()

        expiries = sorted(set(
            str(i.get("expiry", "")).split("T")[0]
            for i in nifty_opts
        ))
        nearest_expiry = expiries[0]

        ltp_round = round(ltp / 50) * 50
        strikes_set = set(range(int(ltp_round - 500), int(ltp_round + 501), 50))

        symmap = {}
        for i in nifty_opts:
            exp = str(i.get("expiry", "")).split("T")[0]
            if exp != nearest_expiry:
                continue
            raw_strike = i.get("strike")
            if raw_strike is None:
                continue
            strike = int(float(raw_strike))
            if strike not in strikes_set:
                continue
            opt_type = i.get("instrument_type")
            symbol   = i.get("tradingsymbol")
            exchange = i.get("exchange", "NFO")
            if symbol:
                key = f"{exchange}:{symbol}"
                symmap[key] = (strike, opt_type)

        if not symmap:
            return _null_response()

        quote_keys = list(symmap.keys())
        quote_data = kite.quote(quote_keys[:400])

        oi_by_strike = {}
        for key, q in quote_data.items():
            info = symmap.get(key)
            if not info:
                continue
            strike, opt_type = info
            if strike not in oi_by_strike:
                oi_by_strike[strike] = {"ce_oi": 0, "pe_oi": 0}
            oi = int(q.get("oi", 0) or 0)
            if opt_type == "CE":
                oi_by_strike[strike]["ce_oi"] = oi
            else:
                oi_by_strike[strike]["pe_oi"] = oi

        if not oi_by_strike:
            return _null_response()

        max_pain = max(
            oi_by_strike,
            key=lambda s: oi_by_strike[s]["ce_oi"] + oi_by_strike[s]["pe_oi"]
        )

        ce_above = {s: v for s, v in oi_by_strike.items() if s > ltp}
        ce_wall  = max(ce_above, key=lambda s: ce_above[s]["ce_oi"]) if ce_above else None
        ce_oi    = oi_by_strike[ce_wall]["ce_oi"] if ce_wall is not None else 0

        pe_below = {s: v for s, v in oi_by_strike.items() if s < ltp}
        pe_wall  = max(pe_below, key=lambda s: pe_below[s]["pe_oi"]) if pe_below else None
        pe_oi    = oi_by_strike[pe_wall]["pe_oi"] if pe_wall is not None else 0

        prev_raw = _r.get("OI_PREV_SNAP")
        prev     = json.loads(prev_raw) if prev_raw else {}

        ce_trend = "Building"
        if prev and prev.get("ce_wall") == ce_wall and ce_wall is not None:
            ce_trend = "Building" if ce_oi > prev.get("ce_oi", 0) else "Unwinding"

        pe_trend = "Building"
        if prev and prev.get("pe_wall") == pe_wall and pe_wall is not None:
            pe_trend = "Building" if pe_oi > prev.get("pe_oi", 0) else "Unwinding"

        ltp_dist = round(abs(ltp - max_pain), 2) if max_pain is not None else None

        snap = {
            "max_pain":                   max_pain,
            "ce_wall":                    ce_wall,
            "ce_oi":                      ce_oi,
            "pe_wall":                    pe_wall,
            "pe_oi":                      pe_oi,
            "timestamp":                  datetime.now(_IST).strftime("%H:%M"),
            "ltp_distance_from_max_pain": ltp_dist,
        }

        current_raw = _r.get("OI_SNAP")
        if current_raw:
            _r.setex("OI_PREV_SNAP", 7200, current_raw)

        _r.set("OI_SNAP", json.dumps(snap))

        return {
            "max_pain":                   max_pain,
            "ce_wall":                    ce_wall,
            "ce_trend":                   ce_trend,
            "pe_wall":                    pe_wall,
            "pe_trend":                   pe_trend,
            "last_fetch":                 snap["timestamp"],
            "ltp_distance_from_max_pain": ltp_dist,
        }

    except Exception as e:
        print(f"[OI] snapshot failed: {e}")
        return _null_response()
