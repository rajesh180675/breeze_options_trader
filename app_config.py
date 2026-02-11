"""
Configuration for Breeze Options Trader.
──────────────────────────────────────────
CRITICAL FIXES:
  • SENSEX uses stock_code "BSESEN" in ICICI Breeze API
  • NIFTY weekly expiry is TUESDAY
  • SENSEX/BSESEN weekly expiry is THURSDAY
  • BANKEX weekly expiry is MONDAY
"""

import streamlit as st
from datetime import datetime, timedelta
import pytz


class Config:
    """Application configuration — single source of truth."""

    IST = pytz.timezone("Asia/Kolkata")

    # ══════════════════════════════════════════════════════════════════════
    # INSTRUMENTS
    # Key       = display name used in UI
    # stock_code= ICICI Breeze API code (BSESEN, not SENSEX!)
    # exchange  = NFO for NSE derivatives, BFO for BSE derivatives
    # lot_size  = contract lot size
    # strike_gap= gap between consecutive strikes
    # expiry_day= weekday name for weekly expiry
    # ══════════════════════════════════════════════════════════════════════

    INSTRUMENTS = {
        "NIFTY": {
            "stock_code": "NIFTY",
            "exchange": "NFO",
            "lot_size": 25,
            "strike_gap": 50,
            "expiry_day": "Tuesday",
            "description": "NIFTY 50 Index",
        },
        "BANKNIFTY": {
            "stock_code": "BANKNIFTY",
            "exchange": "NFO",
            "lot_size": 15,
            "strike_gap": 100,
            "expiry_day": "Wednesday",
            "description": "Bank NIFTY Index",
        },
        "FINNIFTY": {
            "stock_code": "FINNIFTY",
            "exchange": "NFO",
            "lot_size": 25,
            "strike_gap": 50,
            "expiry_day": "Tuesday",
            "description": "NIFTY Financial Services",
        },
        "MIDCPNIFTY": {
            "stock_code": "MIDCPNIFTY",
            "exchange": "NFO",
            "lot_size": 50,
            "strike_gap": 25,
            "expiry_day": "Monday",
            "description": "NIFTY Midcap Select",
        },
        "SENSEX": {
            "stock_code": "BSESEN",       # ← ICICI uses BSESEN
            "exchange": "BFO",
            "lot_size": 10,
            "strike_gap": 100,
            "expiry_day": "Thursday",      # ← Thursday, not Friday
            "description": "BSE SENSEX Index",
        },
        "BANKEX": {
            "stock_code": "BANKEX",
            "exchange": "BFO",
            "lot_size": 15,
            "strike_gap": 100,
            "expiry_day": "Monday",
            "description": "BSE BANKEX Index",
        },
    }

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

    @staticmethod
    def get_next_expiries(instrument: str, count: int = 5) -> list:
        """
        Return the next `count` weekly expiry dates for an instrument.
        Each date is a string in YYYY-MM-DD format.
        """
        inst = Config.INSTRUMENTS.get(instrument)
        if not inst:
            return []

        day_name = inst["expiry_day"]
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2,
            "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6,
        }
        target = day_map.get(day_name, 3)

        now = datetime.now(Config.IST)
        days_ahead = (target - now.weekday()) % 7
        # If today IS expiry day, include it (market might still be open)
        if days_ahead == 0:
            next_exp = now
        else:
            next_exp = now + timedelta(days=days_ahead)

        expiries = []
        for i in range(count):
            d = next_exp + timedelta(weeks=i)
            expiries.append(d.strftime("%Y-%m-%d"))
        return expiries

    @staticmethod
    def get_instrument_display(stock_code: str) -> str:
        """Map API stock_code back to display name."""
        for name, cfg in Config.INSTRUMENTS.items():
            if cfg["stock_code"] == stock_code:
                return name
        return stock_code


def init_session_state():
    """Initialise Streamlit session state with safe defaults."""
    defaults = {
        "authenticated": False,
        "breeze_client": None,
        "current_page": "Dashboard",
        "selected_instrument": "NIFTY",
        "api_key": "",
        "api_secret": "",
        "session_token": "",
        "option_chain_cache": {},
        "cache_timestamp": {},
        "debug_mode": False,
        "error_message": None,
        "success_message": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


class SessionState:
    """Backward-compat wrapper."""

    @staticmethod
    def init_session_state():
        init_session_state()
