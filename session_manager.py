"""
Session Manager for Breeze Options Trader
Handles session state, caching, and persistence
"""

import streamlit as st
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import hashlib
import pickle
from pathlib import Path
import pytz


class SessionManager:
    """
    Manages user sessions, state persistence, and caching
    """
    
    CACHE_DIR = Path(".cache")
    SESSION_FILE = CACHE_DIR / "session_data.pkl"
    IST = pytz.timezone('Asia/Kolkata')
    
    def __init__(self):
        """Initialize session manager"""
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists"""
        if not self.CACHE_DIR.exists():
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def init_session_state():
        """Initialize all session state variables"""
        defaults = {
            # Authentication
            'authenticated': False,
            'breeze_client': None,
            'api_key': '',
            'api_secret': '',
            'session_token': '',
            'login_time': None,
            'user_info': None,
            
            # Trading State
            'selected_instrument': 'NIFTY',
            'selected_expiry': None,
            'selected_strike': None,
            'selected_option_type': 'CE',
            'selected_lots': 1,
            
            # Data Cache
            'positions': [],
            'orders': [],
            'option_chain_data': None,
            'funds_data': None,
            'last_refresh': None,
            
            # UI State
            'current_page': 'Dashboard',
            'show_confirmation': False,
            'pending_order': None,
            
            # Messages
            'error_message': None,
            'success_message': None,
            'warning_message': None,
            
            # Settings
            'auto_refresh': False,
            'refresh_interval': 10,
            'theme': 'light',
            'notifications_enabled': True,
            
            # Order History (in-memory for current session)
            'order_history': [],
            'trade_log': []
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get value from session state"""
        return st.session_state.get(key, default)
    
    @staticmethod
    def set(key: str, value: Any):
        """Set value in session state"""
        st.session_state[key] = value
    
    @staticmethod
    def update(updates: Dict[str, Any]):
        """Update multiple session state values"""
        for key, value in updates.items():
            st.session_state[key] = value
    
    @staticmethod
    def clear():
        """Clear all session state"""
        for key in list(st.session_state.keys()):
            del st.session_state[key]
    
    @staticmethod
    def clear_messages():
        """Clear all message states"""
        st.session_state.error_message = None
        st.session_state.success_message = None
        st.session_state.warning_message = None
    
    @staticmethod
    def set_error(message: str):
        """Set error message"""
        st.session_state.error_message = message
        st.session_state.success_message = None
    
    @staticmethod
    def set_success(message: str):
        """Set success message"""
        st.session_state.success_message = message
        st.session_state.error_message = None
    
    @staticmethod
    def set_warning(message: str):
        """Set warning message"""
        st.session_state.warning_message = message
    
    def save_session(self):
        """Save session data to file for persistence"""
        try:
            session_data = {
                'api_key': st.session_state.get('api_key', ''),
                'api_secret': st.session_state.get('api_secret', ''),
                'session_token': st.session_state.get('session_token', ''),
                'selected_instrument': st.session_state.get('selected_instrument', 'NIFTY'),
                'settings': {
                    'auto_refresh': st.session_state.get('auto_refresh', False),
                    'refresh_interval': st.session_state.get('refresh_interval', 10),
                    'theme': st.session_state.get('theme', 'light'),
                    'notifications_enabled': st.session_state.get('notifications_enabled', True)
                },
                'saved_at': datetime.now(self.IST).isoformat()
            }
            
            with open(self.SESSION_FILE, 'wb') as f:
                pickle.dump(session_data, f)
            
            return True
        except Exception as e:
            print(f"Failed to save session: {e}")
            return False
    
    def load_session(self) -> Optional[Dict]:
        """Load session data from file"""
        try:
            if self.SESSION_FILE.exists():
                with open(self.SESSION_FILE, 'rb') as f:
                    session_data = pickle.load(f)
                return session_data
        except Exception as e:
            print(f"Failed to load session: {e}")
        return None
    
    def restore_session(self) -> bool:
        """Restore session from saved data"""
        session_data = self.load_session()
        
        if session_data:
            st.session_state.api_key = session_data.get('api_key', '')
            st.session_state.api_secret = session_data.get('api_secret', '')
            st.session_state.session_token = session_data.get('session_token', '')
            st.session_state.selected_instrument = session_data.get('selected_instrument', 'NIFTY')
            
            settings = session_data.get('settings', {})
            st.session_state.auto_refresh = settings.get('auto_refresh', False)
            st.session_state.refresh_interval = settings.get('refresh_interval', 10)
            st.session_state.theme = settings.get('theme', 'light')
            st.session_state.notifications_enabled = settings.get('notifications_enabled', True)
            
            return True
        return False
    
    def clear_saved_session(self):
        """Clear saved session file"""
        try:
            if self.SESSION_FILE.exists():
                self.SESSION_FILE.unlink()
            return True
        except Exception as e:
            print(f"Failed to clear session: {e}")
            return False
    
    @staticmethod
    def is_authenticated() -> bool:
        """Check if user is authenticated"""
        return st.session_state.get('authenticated', False)
    
    @staticmethod
    def get_client():
        """Get Breeze client instance"""
        return st.session_state.get('breeze_client', None)
    
    @staticmethod
    def log_order(order_details: Dict):
        """Log order to session history"""
        if 'order_history' not in st.session_state:
            st.session_state.order_history = []
        
        order_log = {
            'timestamp': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            **order_details
        }
        st.session_state.order_history.append(order_log)
    
    @staticmethod
    def log_trade(trade_details: Dict):
        """Log trade to session trade log"""
        if 'trade_log' not in st.session_state:
            st.session_state.trade_log = []
        
        trade_log = {
            'timestamp': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            **trade_details
        }
        st.session_state.trade_log.append(trade_log)
    
    @staticmethod
    def get_order_history() -> list:
        """Get order history"""
        return st.session_state.get('order_history', [])
    
    @staticmethod
    def get_trade_log() -> list:
        """Get trade log"""
        return st.session_state.get('trade_log', [])


class DataCache:
    """
    Caching mechanism for API data
    """
    
    def __init__(self, ttl_seconds: int = 30):
        """
        Initialize cache with TTL
        
        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.ttl = ttl_seconds
        self._cache: Dict[str, Dict] = {}
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments"""
        key_data = 
