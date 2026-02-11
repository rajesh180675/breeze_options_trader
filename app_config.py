"""
Configuration for Breeze Options Trader.
Renamed from config.py to avoid shadowing breeze_connect's internal config.
"""
import streamlit as st
from datetime import datetime, timedelta
import calendar
import pytz

# ═══════════════════════════════════════════════════════════════════════════════
# INSTRUMENTS — VERIFY expiry days with your exchange calendar!
#
#  After SEBI Oct-2024 circular (effective Nov-20-2024):
#    • Only ONE weekly index per exchange
#    • NSE → NIFTY   |  BSE → SENSEX
#    • All others (BANKNIFTY, FINNIFTY, MIDCPNIFTY, BANKEX) → monthly only
#
#  ICICI Breeze stock codes differ from exchange tickers:
#    • SENSEX → "BSESEN"   (not "SENSEX")
# ═══════════════════════════════════════════════════════════════════════════════

DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6,
}

IST = pytz.timezone("Asia/Kolkata")


class Config:

    IST = IST

    # ── Secrets helpers ───────────────────────────────────────────────────
    @staticmethod
    def get_api_key():
        try:
            return st.secrets.get("BREEZE_API_KEY", "")
        except Exception:
            return ""

    @staticmethod
    def get_api_secret():
        try:
            return st.secrets.get("BREEZE_API_SECRET", "")
        except Exception:
            return ""

    @staticmethod
    def get_session_token():
        try:
            return st.secrets.get("BREEZE_SESSION_TOKEN", "")
        except Exception:
            return ""

    # ── Instrument definitions ────────────────────────────────────────────
    INSTRUMENTS = {
        "NIFTY": {
            "exchange": "NFO",
            "stock_code": "NIFTY",
            "lot_size": 25,
            "strike_gap": 50,
            "expiry_type": "weekly",
            "expiry_day": "Tuesday",      # ← VERIFY with NSE
        },
        "BANKNIFTY": {
            "exchange": "NFO",
            "stock_code": "BANKNIFTY",
            "lot_size": 15,
            "strike_gap": 100,
            "expiry_type": "monthly",     # Monthly only post-SEBI rule
            "expiry_day": "Thursday",     # Last Thursday of month
        },
        "SENSEX": {
            "exchange": "BFO",
            "stock_code": "BSESEN",       # ← ICICI code, NOT "SENSEX"
            "lot_size": 10,
            "strike_gap": 100,
            "expiry_type": "weekly",
            "expiry_day": "Thursday",     # ← VERIFY with BSE
        },
        "BANKEX": {
            "exchange": "BFO",
            "stock_code": "BANKEX",
            "lot_size": 15,
            "strike_gap": 100,
            "expiry_type": "monthly",
            "expiry_day": "Thursday",
        },
        "FINNIFTY": {
            "exchange": "NFO",
            "stock_code": "FINNIFTY",
            "lot_size": 25,
            "strike_gap": 50,
            "expiry_type": "monthly",
            "expiry_day": "Thursday",
        },
        "MIDCPNIFTY": {
            "exchange": "NFO",
            "stock_code": "MIDCPNIFTY",
            "lot_size": 50,
            "strike_gap": 25,
            "expiry_type": "monthly",
            "expiry_day": "Thursday",
        },
    }

    ORDER_TYPES = ["Market", "Limit"]
    OPTION_TYPES = ["CE", "PE"]
    MARKET_OPEN = "09:15"
    MARKET_CLOSE = "15:30"

    # ── Expiry calculation ────────────────────────────────────────────────

    @staticmethod
    def get_next_expiries(instrument: str, count: int = 5) -> list:
        """
        Get next `count` expiry dates for an instrument.
        Returns dates as YYYY-MM-DD strings.

        Weekly  → every <expiry_day>
        Monthly → last <expiry_day> of each coming month
        """
        cfg = Config.INSTRUMENTS.get(instrument)
        if not cfg:
            return []

        expiry_type = cfg.get("expiry_type", "weekly")
        expiry_day_name = cfg.get("expiry_day", "Thursday")

        if expiry_type == "monthly":
            return Config._monthly_expiries(expiry_day_name, count)
        else:
            return Config._weekly_expiries(expiry_day_name, count)

    @staticmethod
    def _weekly_expiries(day_name: str, count: int) -> list:
        now = datetime.now(IST)
        target = DAY_MAP[day_name]

        days_ahead = target - now.weekday()
        # Include today if it IS expiry day and before market close
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0:
            mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            if now > mkt_close:
                days_ahead += 7

        first = now + timedelta(days=days_ahead)
        return [(first + timedelta(weeks=i)).strftime("%Y-%m-%d")
                for i in range(count)]

    @staticmethod
    def _monthly_expiries(day_name: str, count: int) -> list:
        now = datetime.now(IST)
        target = DAY_MAP[day_name]
        expiries = []
        year, month = now.year, now.month

        while len(expiries) < count:
            # Find last occurrence of target day in this month
            last_day_of_month = calendar.monthrange(year, month)[1]
            dt = datetime(year, month, last_day_of_month, tzinfo=IST)
            while dt.weekday() != target:
                dt -= timedelta(days=1)

            # Only include if not already passed
            if dt.date() >= now.date():
                expiries.append(dt.strftime("%Y-%m-%d"))

            # Next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

        return expiries

    @staticmethod
    def get_exchange_for_instrument(instrument: str) -> str:
        return Config.INSTRUMENTS.get(instrument, {}).get("exchange", "NFO")


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════

def init_session_state():
    defaults = {
        "authenticated": False,
        "breeze_client": None,
        "positions": [],
        "orders": [],
        "selected_instrument": "NIFTY",
        "selected_expiry": None,
        "selected_strike": None,
        "selected_option_type": "CE",
        "selected_lots": 1,
        "api_key": "",
        "api_secret": "",
        "session_token": "",
        "last_refresh": None,
        "option_chain_data": None,
        "option_chain_cache": {},
        "cache_timestamp": {},
        "error_message": None,
        "success_message": None,
        "warning_message": None,
        "order_history": [],
        "trade_log": [],
        "current_quote": None,
        "sell_option_type": "CE",
        "current_page": "Dashboard",
        "debug_mode": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


class SessionState:
    @staticmethod
    def init_session_state():
        init_session_state()
