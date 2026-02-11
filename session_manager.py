"""
Session & Credential Manager for Breeze Options Trader.
═══════════════════════════════════════════════════════

Handles:
  • Persistent credential storage via st.secrets (API Key, Secret)
  • Daily session token via UI
  • Runtime state management
  • Option chain caching with TTL
  • Order/trade logging per session
  • Toast & message notifications
  • Connection health monitoring
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pytz
import logging

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Manages API credentials with tiered storage:
      1. st.secrets (permanent — API key & secret)
      2. st.session_state (runtime — session token, entered daily)
    """

    @staticmethod
    def get_stored_api_key() -> str:
        """Get API key from Streamlit Secrets (permanent storage)."""
        try:
            return st.secrets.get("BREEZE_API_KEY", "")
        except Exception:
            return ""

    @staticmethod
    def get_stored_api_secret() -> str:
        """Get API secret from Streamlit Secrets (permanent storage)."""
        try:
            return st.secrets.get("BREEZE_API_SECRET", "")
        except Exception:
            return ""

    @staticmethod
    def get_stored_session_token() -> str:
        """Get session token — only from session_state (changes daily)."""
        return st.session_state.get("session_token", "")

    @staticmethod
    def has_stored_credentials() -> bool:
        """Check if API key and secret are stored in secrets."""
        key = CredentialManager.get_stored_api_key()
        secret = CredentialManager.get_stored_api_secret()
        return bool(key and secret)

    @staticmethod
    def get_all_credentials() -> Tuple[str, str, str]:
        """
        Get all credentials, preferring stored secrets over session state.

        Returns: (api_key, api_secret, session_token)
        """
        # API Key: prefer secrets, fall back to session_state
        api_key = CredentialManager.get_stored_api_key()
        if not api_key:
            api_key = st.session_state.get("api_key", "")

        # API Secret: prefer secrets, fall back to session_state
        api_secret = CredentialManager.get_stored_api_secret()
        if not api_secret:
            api_secret = st.session_state.get("api_secret", "")

        # Session Token: always from session_state (changes daily)
        session_token = st.session_state.get("session_token", "")

        return api_key, api_secret, session_token

    @staticmethod
    def save_session_credentials(api_key: str, api_secret: str, session_token: str):
        """Save credentials to session state (runtime only)."""
        st.session_state.api_key = api_key
        st.session_state.api_secret = api_secret
        st.session_state.session_token = session_token
        st.session_state.login_time = datetime.now(
            pytz.timezone("Asia/Kolkata")
        ).isoformat()

    @staticmethod
    def clear_session_credentials():
        """Clear runtime credentials (keeps secrets intact)."""
        st.session_state.api_key = ""
        st.session_state.api_secret = ""
        st.session_state.session_token = ""
        st.session_state.login_time = None

    @staticmethod
    def get_credential_status() -> Dict[str, bool]:
        """Get status of each credential source."""
        return {
            "api_key_in_secrets": bool(CredentialManager.get_stored_api_key()),
            "api_secret_in_secrets": bool(CredentialManager.get_stored_api_secret()),
            "api_key_in_session": bool(st.session_state.get("api_key", "")),
            "api_secret_in_session": bool(st.session_state.get("api_secret", "")),
            "session_token_available": bool(st.session_state.get("session_token", "")),
        }


class SessionManager:
    """
    Centralised session state management.
    All state reads/writes go through here.
    """

    IST = pytz.timezone("Asia/Kolkata")

    # ── Initialisation ────────────────────────────────────────────────────

    @staticmethod
    def init():
        """Initialise all session state variables with safe defaults."""
        defaults = {
            # Authentication
            "authenticated": False,
            "breeze_client": None,
            "api_key": "",
            "api_secret": "",
            "session_token": "",
            "login_time": None,
            "user_name": "",

            # Navigation
            "current_page": "Dashboard",

            # Settings
            "selected_instrument": "NIFTY",
            "debug_mode": False,
            "auto_refresh": False,
            "refresh_interval": 10,

            # Caching
            "option_chain_cache": {},
            "cache_timestamp": {},
            "funds_cache": None,
            "funds_cache_time": None,

            # Messages
            "error_message": None,
            "success_message": None,
            "warning_message": None,

            # Logging
            "order_history": [],
            "trade_log": [],
            "connection_log": [],
        }

        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    # ── Authentication ────────────────────────────────────────────────────

    @staticmethod
    def is_authenticated() -> bool:
        return st.session_state.get("authenticated", False)

    @staticmethod
    def get_client():
        """Get the BreezeClientWrapper instance."""
        return st.session_state.get("breeze_client")

    @staticmethod
    def set_authenticated(value: bool, client=None):
        st.session_state.authenticated = value
        st.session_state.breeze_client = client
        if value:
            st.session_state.login_time = datetime.now(
                SessionManager.IST
            ).isoformat()
            SessionManager.log_connection("Connected")
        else:
            st.session_state.login_time = None
            SessionManager.log_connection("Disconnected")

    @staticmethod
    def get_login_duration() -> Optional[str]:
        """Get how long the user has been logged in."""
        login_time = st.session_state.get("login_time")
        if not login_time:
            return None
        try:
            lt = datetime.fromisoformat(login_time)
            now = datetime.now(SessionManager.IST)
            if lt.tzinfo is None:
                lt = SessionManager.IST.localize(lt)
            diff = now - lt
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{hours}h {minutes}m"
        except Exception:
            return None

    @staticmethod
    def is_session_token_stale() -> bool:
        """
        Check if session token might be stale (logged in > 8 hours ago).
        ICICI tokens typically expire end of day.
        """
        login_time = st.session_state.get("login_time")
        if not login_time:
            return True
        try:
            lt = datetime.fromisoformat(login_time)
            now = datetime.now(SessionManager.IST)
            if lt.tzinfo is None:
                lt = SessionManager.IST.localize(lt)
            return (now - lt).total_seconds() > 8 * 3600
        except Exception:
            return True

    # ── Navigation ────────────────────────────────────────────────────────

    @staticmethod
    def get_page() -> str:
        return st.session_state.get("current_page", "Dashboard")

    @staticmethod
    def set_page(page: str):
        st.session_state.current_page = page

    # ── Caching ───────────────────────────────────────────────────────────

    @staticmethod
    def cache_option_chain(key: str, df):
        """Cache option chain DataFrame with timestamp."""
        st.session_state.option_chain_cache[key] = df
        st.session_state.cache_timestamp[key] = datetime.now()

    @staticmethod
    def get_cached_option_chain(key: str, ttl_seconds: int = 30):
        """Get cached option chain if not expired."""
        cache = st.session_state.get("option_chain_cache", {})
        if key not in cache:
            return None
        ts = st.session_state.get("cache_timestamp", {}).get(key)
        if ts and (datetime.now() - ts).seconds < ttl_seconds:
            return cache[key]
        return None

    @staticmethod
    def clear_cache():
        """Clear all cached data."""
        st.session_state.option_chain_cache = {}
        st.session_state.cache_timestamp = {}
        st.session_state.funds_cache = None
        st.session_state.funds_cache_time = None

    @staticmethod
    def cache_funds(data: Dict):
        """Cache funds data for 60 seconds."""
        st.session_state.funds_cache = data
        st.session_state.funds_cache_time = datetime.now()

    @staticmethod
    def get_cached_funds(ttl_seconds: int = 60) -> Optional[Dict]:
        """Get cached funds if not expired."""
        if not st.session_state.get("funds_cache"):
            return None
        ts = st.session_state.get("funds_cache_time")
        if ts and (datetime.now() - ts).seconds < ttl_seconds:
            return st.session_state.funds_cache
        return None

    # ── Logging ───────────────────────────────────────────────────────────

    @staticmethod
    def log_order(order_details: Dict):
        """Log order to session history."""
        if "order_history" not in st.session_state:
            st.session_state.order_history = []

        entry = {
            "timestamp": datetime.now(SessionManager.IST).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            **order_details,
        }
        st.session_state.order_history.insert(0, entry)  # newest first

        # Keep last 100 entries
        st.session_state.order_history = st.session_state.order_history[:100]
        logger.info(f"Order logged: {order_details}")

    @staticmethod
    def log_trade(trade_details: Dict):
        """Log trade to session trade log."""
        if "trade_log" not in st.session_state:
            st.session_state.trade_log = []

        entry = {
            "timestamp": datetime.now(SessionManager.IST).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            **trade_details,
        }
        st.session_state.trade_log.insert(0, entry)
        st.session_state.trade_log = st.session_state.trade_log[:100]

    @staticmethod
    def log_connection(event: str):
        """Log connection events."""
        if "connection_log" not in st.session_state:
            st.session_state.connection_log = []

        entry = {
            "timestamp": datetime.now(SessionManager.IST).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "event": event,
        }
        st.session_state.connection_log.insert(0, entry)
        st.session_state.connection_log = st.session_state.connection_log[:50]

    @staticmethod
    def get_order_history() -> List[Dict]:
        return st.session_state.get("order_history", [])

    @staticmethod
    def get_trade_log() -> List[Dict]:
        return st.session_state.get("trade_log", [])

    @staticmethod
    def get_connection_log() -> List[Dict]:
        return st.session_state.get("connection_log", [])

    # ── Convenience ───────────────────────────────────────────────────────

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value: Any):
        st.session_state[key] = value

    @staticmethod
    def reset():
        """Full reset — clear everything except secrets."""
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        SessionManager.init()


class NotificationManager:
    """
    Manages toast notifications and persistent messages.
    """

    @staticmethod
    def show_pending_messages():
        """Display and clear any pending messages."""
        if st.session_state.get("error_message"):
            st.error(st.session_state.error_message)
            st.session_state.error_message = None

        if st.session_state.get("success_message"):
            st.success(st.session_state.success_message)
            st.session_state.success_message = None

        if st.session_state.get("warning_message"):
            st.warning(st.session_state.warning_message)
            st.session_state.warning_message = None

    @staticmethod
    def error(msg: str):
        st.session_state.error_message = msg

    @staticmethod
    def success(msg: str):
        st.session_state.success_message = msg

    @staticmethod
    def warning(msg: str):
        st.session_state.warning_message = msg

    @staticmethod
    def toast(msg: str, icon: str = "ℹ️"):
        """Show a non-blocking toast."""
        try:
            st.toast(f"{icon} {msg}")
        except Exception:
            pass  # toast not available in older streamlit

    @staticmethod
    def order_placed(instrument: str, strike: int, opt_type: str,
                     qty: int, action: str):
        """Notification for order placement."""
        NotificationManager.toast(
            f"{action.upper()} {instrument} {strike} {opt_type} x{qty}",
            icon="✅",
        )

    @staticmethod
    def order_failed(reason: str):
        NotificationManager.toast(f"Order failed: {reason}", icon="❌")

    @staticmethod
    def position_closed(instrument: str, strike: int):
        NotificationManager.toast(
            f"Closed {instrument} {strike}", icon="🔄"
        )

    @staticmethod
    def session_warning():
        """Warn if session might be stale."""
        if SessionManager.is_session_token_stale():
            st.warning(
                "⚠️ Your session token may have expired. "
                "ICICI tokens reset daily. Consider reconnecting."
            )
