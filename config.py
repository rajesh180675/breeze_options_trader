"""
Configuration settings for Breeze Options Trader
"""
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz

load_dotenv()

class Config:
    """Application configuration"""
    
    # API Credentials (Store in .env file)
    API_KEY = os.getenv("BREEZE_API_KEY", "")
    API_SECRET = os.getenv("BREEZE_API_SECRET", "")
    SESSION_TOKEN = os.getenv("BREEZE_SESSION_TOKEN", "")
    
    # Timezone
    IST = pytz.timezone('Asia/Kolkata')
    
    # Supported Instruments
    INSTRUMENTS = {
        "NIFTY": {
            "exchange": "NFO",
            "stock_code": "NIFTY",
            "lot_size": 25,
            "strike_gap": 50,
            "description": "NIFTY 50 Index"
        },
        "BANKNIFTY": {
            "exchange": "NFO",
            "stock_code": "BANKNIFTY",
            "lot_size": 15,
            "strike_gap": 100,
            "description": "Bank NIFTY Index"
        },
        "SENSEX": {
            "exchange": "BFO",
            "stock_code": "SENSEX",
            "lot_size": 10,
            "strike_gap": 100,
            "description": "BSE SENSEX Index"
        },
        "BANKEX": {
            "exchange": "BFO",
            "stock_code": "BANKEX",
            "lot_size": 15,
            "strike_gap": 100,
            "description": "BSE BANKEX Index"
        },
        "FINNIFTY": {
            "exchange": "NFO",
            "stock_code": "FINNIFTY",
            "lot_size": 25,
            "strike_gap": 50,
            "description": "NIFTY Financial Services"
        },
        "MIDCPNIFTY": {
            "exchange": "NFO",
            "stock_code": "MIDCPNIFTY",
            "lot_size": 50,
            "strike_gap": 25,
            "description": "NIFTY Midcap Select"
        }
    }
    
    # Order Types
    ORDER_TYPES = ["Market", "Limit"]
    
    # Product Types
    PRODUCT_TYPES = {
        "Intraday": "intraday",
        "Margin": "margin",
        "Cash": "cash"
    }
    
    # Option Types
    OPTION_TYPES = ["CE", "PE"]
    
    # Trading Hours
    MARKET_OPEN = "09:15"
    MARKET_CLOSE = "15:30"
    
    # Expiry Days
    EXPIRY_DAYS = {
        "NIFTY": "Thursday",
        "BANKNIFTY": "Wednesday",
        "FINNIFTY": "Tuesday",
        "MIDCPNIFTY": "Monday",
        "SENSEX": "Friday",
        "BANKEX": "Monday"
    }

    @staticmethod
    def get_next_expiries(instrument: str, count: int = 5) -> list:
        """Get next expiry dates for an instrument"""
        expiries = []
        current_date = datetime.now(Config.IST)
        
        expiry_day = Config.EXPIRY_DAYS.get(instrument, "Thursday")
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2,
            "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        target_day = day_map[expiry_day]
        
        days_ahead = target_day - current_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        
        next_expiry = current_date + timedelta(days=days_ahead)
        
        for i in range(count):
            expiry_date = next_expiry + timedelta(weeks=i)
            expiries.append(expiry_date.strftime("%Y-%m-%d"))
        
        return expiries


class SessionState:
    """Session state management"""
    
    @staticmethod
    def init_session_state():
        """Initialize Streamlit session state variables"""
        import streamlit as st
        
        defaults = {
            'authenticated': False,
            'breeze_client': None,
            'positions': [],
            'orders': [],
            'selected_instrument': 'NIFTY',
            'selected_expiry': None,
            'selected_strike': None,
            'selected_option_type': 'CE',
            'api_key': '',
            'api_secret': '',
            'session_token': '',
            'last_refresh': None,
            'option_chain_data': None,
            'error_message': None,
            'success_message': None
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
