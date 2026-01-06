"""
Session Manager for Breeze Options Trader
Streamlit Cloud Compatible - No file-based caching
"""

import streamlit as st
from datetime import datetime
from typing import Any, Dict, Optional
import pytz


class SessionManager:
    """
    Manages user sessions and state
    Streamlit Cloud compatible - uses only session_state
    """
    
    IST = pytz.timezone('Asia/Kolkata')
    
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
            'sell_option_type': 'CE',
            
            # Data Cache
            'positions': [],
            'orders': [],
            'option_chain_data': None,
            'option_chain_cache': None,
            'option_chain_time': None,
            'funds_data': None,
            'last_refresh': None,
            'current_quote': None,
            
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


class NotificationManager:
    """
    Manages notifications and alerts
    """
    
    @staticmethod
    def show_messages():
        """Display any pending messages"""
        if st.session_state.get('error_message'):
            st.error(st.session_state.error_message)
            st.session_state.error_message = None
        
        if st.session_state.get('success_message'):
            st.success(st.session_state.success_message)
            st.session_state.success_message = None
        
        if st.session_state.get('warning_message'):
            st.warning(st.session_state.warning_message)
            st.session_state.warning_message = None
    
    @staticmethod
    def toast(message: str, icon: str = "ℹ️"):
        """Show toast notification"""
        st.toast(f"{icon} {message}")
    
    @staticmethod
    def order_notification(order_type: str, status: str, details: str = ""):
        """Show order-related notification"""
        if status == "success":
            st.toast(f"✅ {order_type} order placed successfully! {details}")
        elif status == "failed":
            st.toast(f"❌ {order_type} order failed! {details}")
        elif status == "pending":
            st.toast(f"⏳ {order_type} order pending... {details}")


# Initialize global instances
session_manager = SessionManager()
notification_manager = NotificationManager()
