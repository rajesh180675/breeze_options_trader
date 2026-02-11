"""
Breeze Options Trader - Main Application
ICICI Direct Breeze SDK Options Trading Platform

Author: Enhanced Version
Features:
- Robust API response handling
- Comprehensive error handling
- Caching for performance
- Clean separation of concerns
- Type hints throughout
- Extensive input validation
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from functools import wraps
import time
import logging

# Import custom modules
from app_config import Config, SessionState
from breeze_client import BreezeClientWrapper
from utils import Utils, OptionChainAnalyzer

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & SETUP
# ══════════════════════════════════════════════════════════════════════════════

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config must be first Streamlit command
st.set_page_config(
    page_title="Breeze Options Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM CSS
# ══════════════════════════════════════════════════════════════════════════════

CUSTOM_CSS = """
<style>
    /* Main header styling */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1f77b4, #2ecc71);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem;
        margin-bottom: 0;
    }
    
    /* Status indicators */
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.875rem;
        font-weight: 600;
    }
    .status-connected { background: #d4edda; color: #155724; }
    .status-disconnected { background: #f8d7da; color: #721c24; }
    
    /* P&L colors */
    .profit { color: #28a745 !important; font-weight: bold; }
    .loss { color: #dc3545 !important; font-weight: bold; }
    
    /* Card styling */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 0.75rem;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* Button styling */
    .stButton > button { width: 100%; }
    
    /* Order buttons */
    .sell-button button {
        background-color: #dc3545 !important;
        color: white !important;
    }
    .buy-button button {
        background-color: #28a745 !important;
        color: white !important;
    }
    
    /* Info boxes */
    .info-box {
        background: #e7f3ff;
        border-left: 4px solid #2196F3;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    
    /* Warning boxes */
    .warning-box {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Improve dataframe styling */
    .stDataFrame {
        border: 1px solid #e0e0e0;
        border-radius: 0.5rem;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# HELPER CLASSES & FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════


class APIResponse:
    """
    Wrapper for handling Breeze API responses consistently.
    Handles the inconsistency where 'Success' can be dict or list.
    """
    
    def __init__(self, response: Dict[str, Any]):
        self.raw = response
        self.success = response.get("success", False)
        self.message = response.get("message", "Unknown error")
        self._data = self._parse_data(response)
    
    def _parse_data(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the Success field, handling both dict and list formats."""
        if not self.success:
            return {}
        
        data = response.get("data", {})
        if not isinstance(data, dict):
            return {}
        
        success = data.get("Success")
        
        if success is None:
            return {}
        elif isinstance(success, dict):
            return success
        elif isinstance(success, list):
            return success[0] if success and isinstance(success[0], dict) else {}
        else:
            return {}
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get parsed data as dictionary."""
        return self._data
    
    @property
    def data_list(self) -> List[Dict[str, Any]]:
        """Get data as list (for endpoints that return lists)."""
        if not self.success:
            return []
        
        data = self.raw.get("data", {})
        if not isinstance(data, dict):
            return []
        
        success = data.get("Success")
        
        if isinstance(success, list):
            return success
        elif isinstance(success, dict):
            return [success]
        else:
            return []
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a specific field from data."""
        return self._data.get(key, default)


class StateManager:
    """
    Centralized state management for the application.
    Provides type-safe access to session state.
    """
    
    @staticmethod
    def init():
        """Initialize all session state variables."""
        SessionState.init_session_state()
        
        # Additional state for caching
        if "option_chain_cache" not in st.session_state:
            st.session_state.option_chain_cache = {}
        if "cache_timestamp" not in st.session_state:
            st.session_state.cache_timestamp = {}
    
    @staticmethod
    def is_authenticated() -> bool:
        return st.session_state.get("authenticated", False)
    
    @staticmethod
    def get_client() -> Optional[BreezeClientWrapper]:
        return st.session_state.get("breeze_client")
    
    @staticmethod
    def set_authenticated(value: bool, client: Optional[BreezeClientWrapper] = None):
        st.session_state.authenticated = value
        st.session_state.breeze_client = client
    
    @staticmethod
    def get_credentials() -> Tuple[str, str, str]:
        return (
            st.session_state.get("api_key", ""),
            st.session_state.get("api_secret", ""),
            st.session_state.get("session_token", ""),
        )
    
    @staticmethod
    def set_credentials(api_key: str, api_secret: str, session_token: str):
        st.session_state.api_key = api_key
        st.session_state.api_secret = api_secret
        st.session_state.session_token = session_token
    
    @staticmethod
    def cache_option_chain(key: str, data: pd.DataFrame, ttl_seconds: int = 30):
        """Cache option chain data with TTL."""
        st.session_state.option_chain_cache[key] = data
        st.session_state.cache_timestamp[key] = datetime.now()
    
    @staticmethod
    def get_cached_option_chain(key: str, ttl_seconds: int = 30) -> Optional[pd.DataFrame]:
        """Get cached option chain if not expired."""
        if key not in st.session_state.option_chain_cache:
            return None
        
        timestamp = st.session_state.cache_timestamp.get(key)
        if timestamp and (datetime.now() - timestamp).seconds < ttl_seconds:
            return st.session_state.option_chain_cache[key]
        
        return None


def handle_api_error(func):
    """Decorator for handling API errors gracefully."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error in {func.__name__}: {str(e)}")
            st.error(f"❌ An error occurred: {str(e)}")
            return None
    return wrapper


def validate_strike_price(strike: int, strike_gap: int) -> bool:
    """Validate that strike price is valid for the instrument."""
    if strike <= 0:
        return False
    if strike % strike_gap != 0:
        return False
    return True


def validate_quantity(quantity: int, lot_size: int) -> bool:
    """Validate that quantity is a multiple of lot size."""
    if quantity <= 0:
        return False
    if quantity % lot_size != 0:
        return False
    return True


def format_pnl(value: float) -> str:
    """Format P&L with color indicator."""
    if value >= 0:
        return f'<span class="profit">+₹{value:,.2f}</span>'
    else:
        return f'<span class="loss">-₹{abs(value):,.2f}</span>'


def get_atm_strike(spot_price: float, strike_gap: int) -> int:
    """Calculate ATM strike price."""
    return round(spot_price / strike_gap) * strike_gap


def generate_strike_range(atm_strike: int, strike_gap: int, count: int = 10) -> List[int]:
    """Generate a range of strikes around ATM."""
    strikes = []
    for i in range(-count, count + 1):
        strikes.append(atm_strike + (i * strike_gap))
    return strikes


# ══════════════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════


def render_header():
    """Render the application header."""
    st.markdown(
        '<h1 class="main-header">📈 Breeze Options Trader</h1>',
        unsafe_allow_html=True
    )
    st.markdown("---")


def render_login_form():
    """Render the login form in the sidebar."""
    with st.form("login_form", clear_on_submit=False):
        st.subheader("🔐 API Credentials")
        
        api_key, api_secret, session_token = StateManager.get_credentials()
        
        new_api_key = st.text_input(
            "API Key",
            value=api_key,
            type="password",
            placeholder="Enter your API Key",
            help="Your ICICI Direct Breeze API Key"
        )
        
        new_api_secret = st.text_input(
            "API Secret",
            value=api_secret,
            type="password",
            placeholder="Enter your API Secret",
            help="Your ICICI Direct Breeze API Secret"
        )
        
        new_session_token = st.text_input(
            "Session Token",
            value=session_token,
            type="password",
            placeholder="Enter your Session Token",
            help="Daily session token from ICICI Direct"
        )
        
        st.markdown("""
        <div class="info-box">
            <strong>💡 How to get Session Token:</strong><br>
            1. Login to <a href="https://www.icicidirect.com/" target="_blank">ICICI Direct</a><br>
            2. Go to API section<br>
            3. Generate and copy session token
        </div>
        """, unsafe_allow_html=True)
        
        submitted = st.form_submit_button("🔑 Connect", use_container_width=True)
        
        if submitted:
            if not all([new_api_key, new_api_secret, new_session_token]):
                st.warning("⚠️ Please fill in all credentials")
                return
            
            with st.spinner("🔄 Connecting to Breeze API..."):
                client = BreezeClientWrapper(new_api_key, new_api_secret)
                result = client.connect(new_session_token)
                
                if result.get("success"):
                    StateManager.set_authenticated(True, client)
                    StateManager.set_credentials(new_api_key, new_api_secret, new_session_token)
                    st.success("✅ Connected successfully!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    error_msg = result.get("message", "Unknown error")
                    st.error(f"❌ Connection failed: {error_msg}")
                    logger.error(f"Login failed: {error_msg}")


def render_authenticated_sidebar():
    """Render sidebar content for authenticated users."""
    client = StateManager.get_client()
    if not client:
        return
    
    # Connection status
    st.markdown(
        '<span class="status-badge status-connected">✅ Connected</span>',
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    
    # User info
    st.subheader("👤 Account")
    
    try:
        customer_response = APIResponse(client.get_customer_details())
        if customer_response.success:
            name = customer_response.get("name", "User")
            client_code = customer_response.get("client_code", "")
            st.markdown(f"**{name}**")
            if client_code:
                st.caption(f"Client: {client_code}")
        else:
            st.markdown("**User**")
    except Exception as e:
        logger.error(f"Failed to get customer details: {e}")
        st.markdown("**User**")
    
    # Market status
    st.markdown(f"**{Utils.get_market_status()}**")
    
    st.markdown("---")
    
    # Funds
    st.subheader("💰 Funds")
    
    try:
        funds_response = APIResponse(client.get_funds())
        if funds_response.success:
            available = float(funds_response.get("available_margin", 0))
            used = float(funds_response.get("utilized_margin", 0))
            total = available + used
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Available", Utils.format_currency(available))
            with col2:
                st.metric("Used", Utils.format_currency(used))
            
            # Progress bar for margin utilization
            if total > 0:
                utilization = (used / total) * 100
                st.progress(min(utilization / 100, 1.0))
                st.caption(f"Utilization: {utilization:.1f}%")
        else:
            st.info("Unable to fetch funds")
    except Exception as e:
        logger.error(f"Failed to get funds: {e}")
        st.info("Unable to fetch funds")
    
    st.markdown("---")
    
    # Disconnect button
    if st.button("🔓 Disconnect", use_container_width=True, type="secondary"):
        StateManager.set_authenticated(False, None)
        st.rerun()


def render_settings():
    """Render settings section."""
    st.subheader("⚙️ Settings")
    
    selected_instrument = st.selectbox(
        "Default Instrument",
        options=list(Config.INSTRUMENTS.keys()),
        key="selected_instrument",
        help="Select your preferred trading instrument"
    )
    
    # Display instrument info
    inst_config = Config.INSTRUMENTS[selected_instrument]
    with st.expander("ℹ️ Instrument Info"):
        st.markdown(f"""
        - **Exchange:** {inst_config['exchange']}
        - **Lot Size:** {inst_config['lot_size']}
        - **Strike Gap:** {inst_config['strike_gap']}
        - **Expiry Day:** {Config.EXPIRY_DAYS.get(selected_instrument, 'N/A')}
        """)
    
    # Auto-refresh settings
    auto_refresh = st.checkbox("Auto Refresh", value=False, help="Auto-refresh data")
    if auto_refresh:
        refresh_interval = st.slider("Interval (sec)", 5, 60, 10)
        st.caption(f"Data will refresh every {refresh_interval} seconds")


def render_welcome_page():
    """Render welcome page for unauthenticated users."""
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h2>Welcome to Breeze Options Trader</h2>
        <p style="color: #666; font-size: 1.1rem;">
            A powerful platform for trading index options on ICICI Direct
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Features grid
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        ### 📊 Real-time Data
        - Live option chain
        - Real-time quotes
        - Open Interest analysis
        - Put-Call Ratio
        - Max Pain calculation
        """)
    
    with col2:
        st.markdown("""
        ### 💰 Easy Trading
        - Sell Call options
        - Sell Put options
        - Quick square off
        - Position management
        - Order tracking
        """)
    
    with col3:
        st.markdown("""
        ### 🛡️ Risk Management
        - Margin calculator
        - P&L tracking
        - Position limits
        - Risk warnings
        - Order confirmations
        """)
    
    st.markdown("---")
    
    # Supported instruments
    st.subheader("📈 Supported Instruments")
    
    instruments_df = pd.DataFrame([
        {
            "Instrument": name,
            "Exchange": cfg["exchange"],
            "Lot Size": cfg["lot_size"],
            "Strike Gap": cfg["strike_gap"],
            "Expiry": Config.EXPIRY_DAYS.get(name, "N/A")
        }
        for name, cfg in Config.INSTRUMENTS.items()
    ])
    
    st.dataframe(instruments_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    st.info("👈 **Login using the sidebar to start trading**")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_dashboard_tab():
    """Render the main dashboard tab with option chain."""
    client = StateManager.get_client()
    if not client:
        st.error("Not connected")
        return
    
    # Controls row
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        instrument = st.selectbox(
            "Select Instrument",
            options=list(Config.INSTRUMENTS.keys()),
            key="dashboard_instrument"
        )
    
    inst_config = Config.INSTRUMENTS[instrument]
    expiries = Config.get_next_expiries(instrument, 5)
    
    with col2:
        selected_expiry = st.selectbox(
            "Select Expiry",
            options=expiries,
            format_func=Utils.format_expiry_date,
            key="dashboard_expiry"
        )
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh_clicked = st.button("🔄 Refresh", use_container_width=True)
    
    # Cache key for option chain
    cache_key = f"{instrument}_{selected_expiry}"
    
    # Check cache first (unless refresh clicked)
    cached_df = None if refresh_clicked else StateManager.get_cached_option_chain(cache_key)
    
    if cached_df is not None:
        df = cached_df
        st.caption("📦 Using cached data (refreshes every 30 seconds)")
    else:
        # Fetch fresh data
        with st.spinner("Loading option chain..."):
            option_chain = client.get_option_chain(
                stock_code=inst_config["stock_code"],
                exchange=inst_config["exchange"],
                expiry_date=selected_expiry
            )
        
        response = APIResponse(option_chain)
        
        if not response.success:
            st.error(f"Failed to load option chain: {response.message}")
            return
        
        df = OptionChainAnalyzer.process_option_chain(option_chain.get("data", {}))
        
        if df.empty:
            st.warning("No option chain data available")
            return
        
        # Cache the data
        StateManager.cache_option_chain(cache_key, df)
    
    # Display header
    st.subheader(f"📈 {instrument} Option Chain - {Utils.format_expiry_date(selected_expiry)}")
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    pcr = OptionChainAnalyzer.calculate_pcr(df)
    max_pain = OptionChainAnalyzer.get_max_pain(df, inst_config["strike_gap"])
    
    total_call_oi = df[df['right'] == 'Call']['open_interest'].sum() if 'right' in df.columns else 0
    total_put_oi = df[df['right'] == 'Put']['open_interest'].sum() if 'right' in df.columns else 0
    
    with col1:
        pcr_delta = "Bullish" if pcr > 1 else "Bearish" if pcr < 1 else "Neutral"
        st.metric("Put-Call Ratio", f"{pcr:.2f}", delta=pcr_delta)
    
    with col2:
        st.metric("Max Pain", f"{max_pain:,}")
    
    with col3:
        st.metric("Total Call OI", f"{total_call_oi:,.0f}")
    
    with col4:
        st.metric("Total Put OI", f"{total_put_oi:,.0f}")
    
    st.markdown("---")
    
    # Option chain table
    display_columns = ['strike_price', 'right', 'ltp', 'open_interest', 'volume', 
                       'best_bid_price', 'best_offer_price', 'ltp_percent_change']
    available_columns = [col for col in display_columns if col in df.columns]
    
    if available_columns:
        display_df = df[available_columns].copy()
        
        # Rename columns for better display
        column_names = {
            'strike_price': 'Strike',
            'right': 'Type',
            'ltp': 'LTP',
            'open_interest': 'OI',
            'volume': 'Volume',
            'best_bid_price': 'Bid',
            'best_offer_price': 'Ask',
            'ltp_percent_change': 'Change %'
        }
        display_df = display_df.rename(columns=column_names)
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            hide_index=True
        )
    else:
        st.dataframe(df, use_container_width=True, height=400)


# ══════════════════════════════════════════════════════════════════════════════
# SELL OPTIONS TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_sell_options_tab():
    """Render the sell options tab."""
    client = StateManager.get_client()
    if not client:
        st.error("Not connected")
        return
    
    st.subheader("💰 Sell Options")
    
    # Two-column layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Contract Selection")
        
        # Instrument
        instrument = st.selectbox(
            "Instrument",
            options=list(Config.INSTRUMENTS.keys()),
            key="sell_instrument"
        )
        inst_config = Config.INSTRUMENTS[instrument]
        
        # Expiry
        expiries = Config.get_next_expiries(instrument, 5)
        expiry = st.selectbox(
            "Expiry Date",
            options=expiries,
            format_func=Utils.format_expiry_date,
            key="sell_expiry"
        )
        
        # Option type
        option_type = st.radio(
            "Option Type",
            options=["CE (Call)", "PE (Put)"],
            horizontal=True,
            key="sell_option_type"
        )
        option_type_code = "CE" if "CE" in option_type else "PE"
        
        # Strike price with validation
        strike_price = st.number_input(
            "Strike Price",
            min_value=0,
            step=inst_config["strike_gap"],
            value=0,
            key="sell_strike",
            help=f"Must be a multiple of {inst_config['strike_gap']}"
        )
        
        # Validation
        if strike_price > 0 and strike_price % inst_config["strike_gap"] != 0:
            st.warning(f"⚠️ Strike should be a multiple of {inst_config['strike_gap']}")
    
    with col2:
        st.markdown("#### Order Details")
        
        # Lots
        lots = st.number_input(
            "Number of Lots",
            min_value=1,
            max_value=100,
            value=1,
            key="sell_lots"
        )
        
        quantity = lots * inst_config["lot_size"]
        
        st.info(f"""
        **Order Summary:**
        - Lots: {lots}
        - Lot Size: {inst_config['lot_size']}
        - **Total Quantity: {quantity}**
        """)
        
        # Order type
        order_type = st.radio(
            "Order Type",
            options=["Market", "Limit"],
            horizontal=True,
            key="sell_order_type"
        )
        
        # Limit price (only if limit order)
        limit_price = 0.0
        if order_type == "Limit":
            limit_price = st.number_input(
                "Limit Price (₹)",
                min_value=0.0,
                step=0.05,
                format="%.2f",
                key="sell_limit_price"
            )
            if limit_price <= 0:
                st.warning("⚠️ Please enter a valid limit price")
    
    st.markdown("---")
    
    # Action buttons row
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 Get Quote", use_container_width=True, disabled=strike_price <= 0):
            with st.spinner("Fetching quote..."):
                quote = client.get_quotes(
                    stock_code=inst_config["stock_code"],
                    exchange=inst_config["exchange"],
                    expiry_date=expiry,
                    strike_price=strike_price,
                    option_type=option_type_code
                )
                
                response = APIResponse(quote)
                
                if response.success:
                    # Handle list response for quotes
                    quote_data = response.data_list[0] if response.data_list else response.data
                    
                    ltp = quote_data.get('ltp', 'N/A')
                    bid = quote_data.get('best_bid_price', 'N/A')
                    ask = quote_data.get('best_offer_price', 'N/A')
                    
                    st.success(f"""
                    **Quote Retrieved:**
                    - **LTP:** ₹{ltp}
                    - **Bid:** ₹{bid}
                    - **Ask:** ₹{ask}
                    """)
                else:
                    st.error(f"Failed to get quote: {response.message}")
    
    with col2:
        if st.button("💰 Calculate Margin", use_container_width=True, disabled=strike_price <= 0):
            with st.spinner("Calculating margin..."):
                margin = client.get_margin_required(
                    stock_code=inst_config["stock_code"],
                    exchange=inst_config["exchange"],
                    expiry_date=expiry,
                    strike_price=strike_price,
                    option_type=option_type_code,
                    action="sell",
                    quantity=quantity
                )
                
                response = APIResponse(margin)
                
                if response.success:
                    required_margin = response.get('required_margin', 'N/A')
                    st.info(f"**Required Margin:** ₹{required_margin}")
                else:
                    st.warning("Could not calculate margin")
    
    st.markdown("---")
    
    # Risk warning
    st.markdown("""
    <div class="warning-box">
        <strong>⚠️ RISK WARNING</strong><br>
        You are about to <strong>SELL</strong> an option. Option selling carries 
        <strong>unlimited risk potential</strong>. Ensure you understand the risks 
        and have adequate margin before proceeding.
    </div>
    """, unsafe_allow_html=True)
    
    # Confirmation and order placement
    confirm = st.checkbox(
        "I understand the risks and confirm the order details",
        key="sell_confirm"
    )
    
    # Validate before enabling button
    can_place_order = (
        confirm and 
        strike_price > 0 and 
        strike_price % inst_config["strike_gap"] == 0 and
        (order_type == "Market" or limit_price > 0)
    )
    
    if st.button(
        f"🔴 SELL {option_type_code}",
        type="primary",
        use_container_width=True,
        disabled=not can_place_order
    ):
        with st.spinner("Placing order..."):
            if option_type_code == "CE":
                result = client.sell_call(
                    stock_code=inst_config["stock_code"],
                    exchange=inst_config["exchange"],
                    expiry_date=expiry,
                    strike_price=strike_price,
                    quantity=quantity,
                    order_type=order_type.lower(),
                    price=limit_price
                )
            else:
                result = client.sell_put(
                    stock_code=inst_config["stock_code"],
                    exchange=inst_config["exchange"],
                    expiry_date=expiry,
                    strike_price=strike_price,
                    quantity=quantity,
                    order_type=order_type.lower(),
                    price=limit_price
                )
            
            response = APIResponse(result)
            
            if response.success:
                order_id = response.get('order_id', 'N/A')
                message = response.get('message', 'Order submitted')
                
                st.success(f"""
                ✅ **Order Placed Successfully!**
                
                - **Order ID:** {order_id}
                - **Status:** {message}
                - **Contract:** {instrument} {strike_price} {option_type_code}
                - **Quantity:** {quantity}
                """)
                st.balloons()
                
                logger.info(f"Order placed: {order_id}")
            else:
                st.error(f"❌ Order failed: {response.message}")
                logger.error(f"Order failed: {response.message}")


# ══════════════════════════════════════════════════════════════════════════════
# SQUARE OFF TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_square_off_tab():
    """Render the square off positions tab."""
    client = StateManager.get_client()
    if not client:
        st.error("Not connected")
        return
    
    st.subheader("🔄 Square Off Positions")
    
    # Fetch positions
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    
    response = APIResponse(positions)
    
    if not response.success:
        st.error(f"Failed to load positions: {response.message}")
        return
    
    # Get positions list
    position_list = response.data_list
    
    if not position_list:
        st.info("📭 No open positions")
        return
    
    # Filter option positions with non-zero quantity
    option_positions = [
        p for p in position_list
        if (p.get("product_type", "").lower() == "options" and 
            int(p.get("quantity", 0)) != 0)
    ]
    
    if not option_positions:
        st.info("📭 No open option positions to square off")
        return
    
    st.success(f"Found **{len(option_positions)}** open option position(s)")
    
    # Display positions table
    display_data = []
    for p in option_positions:
        qty = int(p.get("quantity", 0))
        avg = float(p.get("average_price", 0))
        ltp = float(p.get("ltp", avg))
        
        # Calculate P&L
        if qty > 0:  # Long
            pnl = (ltp - avg) * qty
        else:  # Short
            pnl = (avg - ltp) * abs(qty)
        
        display_data.append({
            "Instrument": p.get("stock_code", ""),
            "Strike": p.get("strike_price", ""),
            "Type": p.get("right", ""),
            "Expiry": p.get("expiry_date", ""),
            "Qty": qty,
            "Avg Price": f"₹{avg:.2f}",
            "LTP": f"₹{ltp:.2f}",
            "P&L": f"₹{pnl:+,.2f}",
            "Position": "Long" if qty > 0 else "Short"
        })
    
    df = pd.DataFrame(display_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Individual square off
    st.markdown("#### Square Off Individual Position")
    
    position_labels = [
        f"{p['stock_code']} {p['strike_price']} {p['right']} | Qty: {p['quantity']}"
        for p in option_positions
    ]
    
    selected_idx = st.selectbox(
        "Select Position",
        options=range(len(position_labels)),
        format_func=lambda x: position_labels[x],
        key="squareoff_position"
    )
    
    selected_pos = option_positions[selected_idx]
    qty = abs(int(selected_pos.get("quantity", 0)))
    position_type = "long" if int(selected_pos.get("quantity", 0)) > 0 else "short"
    
    col1, col2 = st.columns(2)
    
    with col1:
        sq_order_type = st.radio(
            "Order Type",
            options=["Market", "Limit"],
            horizontal=True,
            key="sq_order_type"
        )
    
    with col2:
        sq_limit_price = 0.0
        if sq_order_type == "Limit":
            sq_limit_price = st.number_input(
                "Limit Price",
                min_value=0.0,
                step=0.05,
                key="sq_limit_price"
            )
    
    sq_qty = st.slider(
        "Quantity to Square Off",
        min_value=1,
        max_value=qty,
        value=qty,
        key="sq_qty"
    )
    
    action_text = "BUY" if position_type == "short" else "SELL"
    action_color = "buy-button" if position_type == "short" else "sell-button"
    
    st.markdown(f'<div class="{action_color}">', unsafe_allow_html=True)
    if st.button(
        f"🔄 Square Off ({action_text} {sq_qty})",
        type="primary",
        use_container_width=True
    ):
        with st.spinner("Squaring off position..."):
            result = client.square_off_position(
                stock_code=selected_pos.get("stock_code"),
                exchange=selected_pos.get("exchange_code"),
                expiry_date=selected_pos.get("expiry_date"),
                strike_price=int(selected_pos.get("strike_price", 0)),
                option_type=selected_pos.get("right", "").upper(),
                quantity=sq_qty,
                current_position=position_type,
                order_type=sq_order_type.lower(),
                price=sq_limit_price
            )
            
            response = APIResponse(result)
            
            if response.success:
                st.success("✅ Position squared off successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ Square off failed: {response.message}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Square off all
    st.markdown("#### ⚡ Emergency: Square Off All")
    
    st.warning("⚠️ This will close **ALL** open option positions at market price!")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        confirm_all = st.checkbox(
            "I confirm I want to square off ALL positions",
            key="confirm_square_all"
        )
    
    with col2:
        if st.button(
            "🔴 SQUARE OFF ALL",
            type="secondary",
            use_container_width=True,
            disabled=not confirm_all
        ):
            with st.spinner("Squaring off all positions..."):
                results = client.square_off_all()
                
                success_count = sum(1 for r in results if r.get("success", False))
                fail_count = len(results) - success_count
                
                if success_count > 0:
                    st.success(f"✅ Squared off {success_count} position(s)")
                if fail_count > 0:
                    st.warning(f"⚠️ Failed to square off {fail_count} position(s)")
                
                time.sleep(1)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_orders_tab():
    """Render the orders management tab."""
    client = StateManager.get_client()
    if not client:
        st.error("Not connected")
        return
    
    st.subheader("📋 Order Management")
    
    # Filters
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        exchange_filter = st.selectbox(
            "Exchange",
            options=["All", "NFO", "BFO"],
            key="order_exchange"
        )
    
    with col2:
        from_date = st.date_input(
            "From Date",
            value=datetime.now().date() - timedelta(days=7),
            key="order_from"
        )
    
    with col3:
        to_date = st.date_input(
            "To Date",
            value=datetime.now().date(),
            key="order_to"
        )
    
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", key="refresh_orders", use_container_width=True):
            st.rerun()
    
    # Fetch orders
    with st.spinner("Loading orders..."):
        orders = client.get_order_list(
            exchange="" if exchange_filter == "All" else exchange_filter,
            from_date=from_date.strftime("%Y-%m-%d"),
            to_date=to_date.strftime("%Y-%m-%d")
        )
    
    response = APIResponse(orders)
    
    if not response.success:
        st.error(f"Failed to load orders: {response.message}")
        return
    
    order_list = response.data_list
    
    if not order_list:
        st.info("📭 No orders found for the selected period")
        return
    
    # Summary metrics
    total_orders = len(order_list)
    executed = sum(1 for o in order_list if o.get("order_status", "").lower() == "executed")
    pending = sum(1 for o in order_list if o.get("order_status", "").lower() in ["pending", "open"])
    rejected = sum(1 for o in order_list if o.get("order_status", "").lower() == "rejected")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Orders", total_orders)
    col2.metric("Executed", executed)
    col3.metric("Pending", pending)
    col4.metric("Rejected", rejected)
    
    st.markdown("---")
    
    # Orders table
    display_columns = ['order_id', 'stock_code', 'action', 'quantity', 'price', 
                       'order_type', 'order_status', 'order_datetime']
    
    df = pd.DataFrame(order_list)
    available_cols = [c for c in display_columns if c in df.columns]
    
    if available_cols:
        display_df = df[available_cols].copy()
        column_names = {
            'order_id': 'Order ID',
            'stock_code': 'Instrument',
            'action': 'Action',
            'quantity': 'Qty',
            'price': 'Price',
            'order_type': 'Type',
            'order_status': 'Status',
            'order_datetime': 'Time'
        }
        display_df = display_df.rename(columns=column_names)
        st.dataframe(display_df, use_container_width=True, height=400, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, height=400)
    
    # Pending order actions
    pending_orders = [o for o in order_list if o.get("order_status", "").lower() in ["pending", "open"]]
    
    if pending_orders:
        st.markdown("---")
        st.markdown("#### Manage Pending Orders")
        
        order_labels = [
            f"{o.get('order_id', 'N/A')} | {o.get('stock_code', '')} {o.get('action', '')} {o.get('quantity', '')}"
            for o in pending_orders
        ]
        
        selected_order_idx = st.selectbox(
            "Select Order",
            options=range(len(order_labels)),
            format_func=lambda x: order_labels[x],
            key="manage_order"
        )
        
        selected_order = pending_orders[selected_order_idx]
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("❌ Cancel Order", use_container_width=True, type="secondary"):
                with st.spinner("Cancelling order..."):
                    result = client.cancel_order(
                        order_id=selected_order.get("order_id"),
                        exchange=selected_order.get("exchange_code")
                    )
                    
                    response = APIResponse(result)
                    
                    if response.success:
                        st.success("✅ Order cancelled!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to cancel: {response.message}")
        
        with col2:
            with st.expander("✏️ Modify Order"):
                new_price = st.number_input(
                    "New Price",
                    min_value=0.0,
                    value=float(selected_order.get("price", 0)),
                    step=0.05,
                    key="modify_price"
                )
                
                new_qty = st.number_input(
                    "New Quantity",
                    min_value=1,
                    value=int(selected_order.get("quantity", 1)),
                    key="modify_qty"
                )
                
                if st.button("💾 Save Changes", use_container_width=True):
                    with st.spinner("Modifying order..."):
                        result = client.modify_order(
                            order_id=selected_order.get("order_id"),
                            exchange=selected_order.get("exchange_code"),
                            quantity=new_qty,
                            price=new_price
                        )
                        
                        response = APIResponse(result)
                        
                        if response.success:
                            st.success("✅ Order modified!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to modify: {response.message}")


# ══════════════════════════════════════════════════════════════════════════════
# POSITIONS TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_positions_tab():
    """Render the positions tab."""
    client = StateManager.get_client()
    if not client:
        st.error("Not connected")
        return
    
    st.subheader("📍 Current Positions")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Refresh", key="refresh_positions", use_container_width=True):
            st.rerun()
    
    # Fetch positions
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    
    response = APIResponse(positions)
    
    if not response.success:
        st.error(f"Failed to load positions: {response.message}")
        return
    
    position_list = response.data_list
    
    if not position_list:
        st.info("📭 No open positions")
        return
    
    # Calculate P&L for each position
    total_pnl = 0.0
    total_investment = 0.0
    
    enhanced_positions = []
    for pos in position_list:
        qty = int(pos.get("quantity", 0))
        avg_price = float(pos.get("average_price", 0))
        ltp = float(pos.get("ltp", avg_price))
        
        if qty == 0:
            continue
        
        # Calculate P&L
        if qty > 0:  # Long position
            pnl = (ltp - avg_price) * qty
            investment = avg_price * qty
        else:  # Short position
            pnl = (avg_price - ltp) * abs(qty)
            investment = avg_price * abs(qty)
        
        total_pnl += pnl
        total_investment += investment
        
        enhanced_positions.append({
            **pos,
            "calculated_pnl": pnl,
            "pnl_percent": (pnl / investment * 100) if investment > 0 else 0,
            "position_type": "Long" if qty > 0 else "Short"
        })
    
    if not enhanced_positions:
        st.info("📭 No active positions")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Positions", len(enhanced_positions))
    
    with col2:
        long_count = sum(1 for p in enhanced_positions if p["position_type"] == "Long")
        st.metric("Long", long_count)
    
    with col3:
        short_count = sum(1 for p in enhanced_positions if p["position_type"] == "Short")
        st.metric("Short", short_count)
    
    with col4:
        pnl_color = "normal" if total_pnl >= 0 else "inverse"
        st.metric(
            "Total P&L",
            f"₹{total_pnl:+,.2f}",
            delta=f"{(total_pnl/total_investment*100):+.2f}%" if total_investment > 0 else "0%",
            delta_color=pnl_color
        )
    
    st.markdown("---")
    
    # Positions table
    display_data = []
    for p in enhanced_positions:
        display_data.append({
            "Instrument": p.get("stock_code", ""),
            "Exchange": p.get("exchange_code", ""),
            "Expiry": p.get("expiry_date", ""),
            "Strike": p.get("strike_price", ""),
            "Type": p.get("right", ""),
            "Position": p["position_type"],
            "Qty": p.get("quantity", 0),
            "Avg Price": f"₹{float(p.get('average_price', 0)):.2f}",
            "LTP": f"₹{float(p.get('ltp', 0)):.2f}",
            "P&L": f"₹{p['calculated_pnl']:+,.2f}",
            "P&L %": f"{p['pnl_percent']:+.2f}%"
        })
    
    df = pd.DataFrame(display_data)
    
    # Apply styling
    def highlight_pnl(val):
        if isinstance(val, str) and '₹' in val:
            if val.startswith('₹-') or val.startswith('-₹'):
                return 'color: #dc3545; font-weight: bold'
            elif '+' in val or (val.replace('₹', '').replace(',', '').replace('.', '').isdigit() and float(val.replace('₹', '').replace(',', '')) > 0):
                return 'color: #28a745; font-weight: bold'
        return ''
    
    st.dataframe(df, use_container_width=True, height=400, hide_index=True)
    
    st.markdown("---")
    
    # Position details expanders
    st.markdown("#### 📊 Position Details")
    
    for pos in enhanced_positions:
        pnl = pos['calculated_pnl']
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        
        with st.expander(
            f"{pnl_emoji} {pos.get('stock_code')} {pos.get('strike_price')} {pos.get('right')} | "
            f"Qty: {pos.get('quantity')} | P&L: ₹{pnl:+,.2f}"
        ):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**Contract Details**")
                st.write(f"Exchange: {pos.get('exchange_code')}")
                st.write(f"Expiry: {pos.get('expiry_date')}")
                st.write(f"Strike: {pos.get('strike_price')}")
                st.write(f"Type: {pos.get('right')}")
            
            with col2:
                st.markdown("**Position Details**")
                st.write(f"Quantity: {pos.get('quantity')}")
                st.write(f"Position: {pos['position_type']}")
                st.write(f"Avg Price: ₹{float(pos.get('average_price', 0)):.2f}")
                st.write(f"LTP: ₹{float(pos.get('ltp', 0)):.2f}")
            
            with col3:
                st.markdown("**P&L Analysis**")
                st.write(f"P&L: ₹{pnl:+,.2f}")
                st.write(f"P&L %: {pos['pnl_percent']:+.2f}%")
                
                # Break-even analysis for short positions
                if pos['position_type'] == 'Short':
                    avg = float(pos.get('average_price', 0))
                    st.write(f"Break-even: ₹{avg:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════


def render_main_dashboard():
    """Render the main dashboard with all tabs."""
    tab_names = [
        "📊 Dashboard",
        "💰 Sell Options",
        "🔄 Square Off",
        "📋 Orders",
        "📍 Positions"
    ]
    
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        render_dashboard_tab()
    
    with tabs[1]:
        render_sell_options_tab()
    
    with tabs[2]:
        render_square_off_tab()
    
    with tabs[3]:
        render_orders_tab()
    
    with tabs[4]:
        render_positions_tab()


def main():
    """Main application entry point."""
    
    # Initialize state
    StateManager.init()
    
    # Render header
    render_header()
    
    # Sidebar
    with st.sidebar:
        if not StateManager.is_authenticated():
            render_login_form()
        else:
            render_authenticated_sidebar()
        
        st.markdown("---")
        render_settings()
        
        # Footer
        st.markdown("---")
        st.caption("Breeze Options Trader v2.0")
        st.caption("© 2024 - For educational purposes")
    
    # Main content
    if not StateManager.is_authenticated():
        render_welcome_page()
    else:
        render_main_dashboard()


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
