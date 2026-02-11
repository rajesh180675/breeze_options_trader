"""
Configuration for Breeze Options Trader.
"""

import streamlit as st
from datetime import datetime, timedelta
import pytz


class Config:
    """Application configuration — single source of truth."""

    IST = pytz.timezone("Asia/Kolkata")

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
            "stock_code": "BSESEN",
            "exchange": "BFO",
            "lot_size": 10,
            "strike_gap": 100,
            "expiry_day": "Thursday",
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
    def get_next_expiries(instrument: str, count: int = 5) -> list:
        inst = Config.INSTRUMENTS.get(instrument)
        if not inst:
            return []
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2,
            "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6,
        }
        target = day_map.get(inst["expiry_day"], 3)
        now = datetime.now(Config.IST)
        days_ahead = (target - now.weekday()) % 7
        next_exp = now if days_ahead == 0 else now + timedelta(days=days_ahead)
        return [(next_exp + timedelta(weeks=i)).strftime("%Y-%m-%d")
                for i in range(count)]

    @staticmethod
    def get_instrument_display(stock_code: str) -> str:
        for name, cfg in Config.INSTRUMENTS.items():
            if cfg["stock_code"] == stock_code:
                return name
        return stock_code


class SessionState:
    """Backward-compat wrapper — delegates to SessionManager."""

    @staticmethod
    def init_session_state():
        from session_manager import SessionManager
        SessionManager.init()
