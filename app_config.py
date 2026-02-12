"""
Configuration — instruments, expiry logic, session state defaults.
"""
import streamlit as st
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")

# ── Instruments ───────────────────────────────────────────────────────────────
# stock_code = what Breeze API expects (BSESEN not SENSEX)
# expiry_day = weekly expiry weekday

INSTRUMENTS = {
    "NIFTY":      {"stock_code": "NIFTY",      "exchange": "NFO", "lot": 65,  "gap": 50,  "expiry_day": "Tuesday",   "desc": "NIFTY 50"},
    "BANKNIFTY":  {"stock_code": "BANKNIFTY",  "exchange": "NFO", "lot": 15,  "gap": 100, "expiry_day": "Wednesday", "desc": "Bank NIFTY"},
    "FINNIFTY":   {"stock_code": "FINNIFTY",   "exchange": "NFO", "lot": 25,  "gap": 50,  "expiry_day": "Tuesday",   "desc": "NIFTY Financial"},
    "MIDCPNIFTY": {"stock_code": "MIDCPNIFTY", "exchange": "NFO", "lot": 50,  "gap": 25,  "expiry_day": "Monday",    "desc": "NIFTY Midcap"},
    "SENSEX":     {"stock_code": "BSESEN",     "exchange": "BFO", "lot": 20,  "gap": 100, "expiry_day": "Thursday",  "desc": "BSE SENSEX"},
    "BANKEX":     {"stock_code": "BANKEX",     "exchange": "BFO", "lot": 15,  "gap": 100, "expiry_day": "Monday",    "desc": "BSE BANKEX"},
}

DAY_MAP = {"Monday": 0, "Tuesday": 1, "Wednesday": 2,
           "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def get_expiries(instrument: str, n: int = 5) -> list:
    """Next n weekly expiry dates as YYYY-MM-DD strings."""
    cfg = INSTRUMENTS.get(instrument)
    if not cfg:
        return []
    target = DAY_MAP[cfg["expiry_day"]]
    now = datetime.now(IST)
    ahead = (target - now.weekday()) % 7
    nxt = now if ahead == 0 else now + timedelta(days=ahead)
    return [(nxt + timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)]


def display_name(stock_code: str) -> str:
    """Map API code back to display name (BSESEN → SENSEX)."""
    for name, cfg in INSTRUMENTS.items():
        if cfg["stock_code"] == stock_code:
            return name
    return stock_code


def init_state():
    """Initialise session state with safe defaults."""
    for k, v in {
        "authenticated": False, "breeze": None,
        "api_key": "", "api_secret": "", "session_token": "",
        "login_time": None, "user_name": "",
        "page": "Dashboard", "selected_instrument": "NIFTY",
        "debug": False, "oc_cache": {}, "oc_ts": {},
        "activity_log": [],
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v
