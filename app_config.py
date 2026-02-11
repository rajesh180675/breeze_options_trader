"""
Configuration settings for Breeze Options Trader
"""
import streamlit as st
from datetime import datetime, timedelta
import pytz


class Config:
    """Application configuration"""

    IST = pytz.timezone("Asia/Kolkata")

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

    INSTRUMENTS = {
        "NIFTY": {"exchange": "NFO", "stock_code": "NIFTY", "lot_size": 25, "strike_gap": 50},
        "BANKNIFTY": {"exchange": "NFO", "stock_code": "BANKNIFTY", "lot_size": 15, "strike_gap": 100},
        "SENSEX": {"exchange": "BFO", "stock_code": "SENSEX", "lot_size": 10, "strike_gap": 100},
        "BANKEX": {"exchange": "BFO", "stock_code": "BANKEX", "lot_size": 15, "strike_gap": 100},
        "FINNIFTY": {"exchange": "NFO", "stock_code": "FINNIFTY", "lot_size": 25, "strike_gap": 50},
        "MIDCPNIFTY": {"exchange": "NFO", "stock_code": "MIDCPNIFTY", "lot_size": 50, "strike_gap": 25},
    }

    ORDER_TYPES = ["Market", "Limit"]
    OPTION_TYPES = ["CE", "PE"]
    MARKET_OPEN = "09:15"
    MARKET_CLOSE = "15:30"

    EXPIRY_DAYS = {
        "NIFTY": "Thursday",
        "BANKNIFTY": "Wednesday",
        "FINNIFTY": "Tuesday",
        "MIDCPNIFTY": "Monday",
        "SENSEX": "Friday",
        "BANKEX": "Monday",
    }

    @staticmethod
    def get_next_expiries(instrument: str, count: int = 5) -> list:
        expiries = []
        current_date = datetime.now(Config.IST)
        expiry_day = Config.EXPIRY_DAYS.get(instrument, "Thursday")
        day_map = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
        target_day = day_map[expiry_day]
        days_ahead = target_day - current_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_expiry = current_date + timedelta(days=days_ahead)
        for i in range(count):
            expiry_date = next_expiry + timedelta(weeks=i)
            expiries.append(expiry_date.strftime("%Y-%m-%d"))
        return expiries


def init_session_state():
    """Initialize Streamlit session state variables"""
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
        "error_message": None,
        "success_message": None,
        "warning_message": None,
        "order_history": [],
        "trade_log": [],
        "current_quote": None,
        "sell_option_type": "CE",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


class SessionState:
    """Wrapper for backward compatibility"""

    @staticmethod
    def init_session_state():
        init_session_state()
