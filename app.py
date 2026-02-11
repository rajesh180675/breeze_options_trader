"""
Breeze Options Trader - Main Application
ICICI Direct Breeze SDK Options Trading Platform

Version: 2.1 - Fixed position type detection
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import wraps
import time
import logging

from app_config import Config, SessionState
from breeze_client import BreezeClientWrapper
from utils import Utils, OptionChainAnalyzer

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION & SETUP
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1f77b4, #2ecc71);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem;
    }
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.875rem;
        font-weight: 600;
    }
    .status-connected { background: #d4edda; color: #155724; }
    .profit { color: #28a745 !important; font-weight: bold; }
    .loss { color: #dc3545 !important; font-weight: bold; }
    .position-long { 
        background: #d4edda; 
        color: #155724; 
        padding: 2px 8px; 
        border-radius: 4px;
        font-weight: bold;
    }
    .position-short { 
        background: #f8d7da; 
        color: #721c24; 
        padding: 2px 8px; 
        border-radius: 4px;
        font-weight: bold;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 0.75rem;
        color: white;
    }
    .stButton > button { width: 100%; }
    .warning-box {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    .info-box {
        background: #e7f3ff;
        border-left: 4px solid #2196F3;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.5rem 0.5rem 0;
    }
    .debug-box {
        background: #f5f5f5;
        border: 1px solid #ddd;
        padding: 0.5rem;
        font-family: monospace;
        font-size: 0.8rem;
        overflow-x: auto;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# POSITION TYPE DETECTION - CRITICAL FIX
# ══════════════════════════════════════════════════════════════════════════════


def get_position_type(position: Dict[str, Any]) -> str:
    """
    Determine if a position is LONG or SHORT.
    
    CRITICAL: Breeze API returns POSITIVE quantity for BOTH long and short.
    We must check the 'action' field to determine actual position type.
    
    Long Position (Bought):
        - action = "buy"
        - You paid premium
        - Risk: Limited to premium paid
        - To close: SELL
        
    Short Position (Sold):
        - action = "sell" 
        - You received premium
        - Risk: Unlimited (for calls) / Large (for puts)
        - To close: BUY
    
    Returns: "long" or "short"
    """
    
    # Method 1: Check 'action' field (most reliable for Breeze API)
    action = str(position.get("action", "")).lower().strip()
    if action == "sell":
        return "short"
    elif action == "buy":
        return "long"
    
    # Method 2: Check 'position_type' field if available
    pos_type = str(position.get("position_type", "")).lower().strip()
    if pos_type in ["short", "sell", "sold", "s"]:
        return "short"
    elif pos_type in ["long", "buy", "bought", "b"]:
        return "long"
    
    # Method 3: Check buy_quantity vs sell_quantity
    buy_qty = _safe_int(position.get("buy_quantity", 0))
    sell_qty = _safe_int(position.get("sell_quantity", 0))
    
    if sell_qty > 0 and buy_qty == 0:
        return "short"
    elif buy_qty > 0 and sell_qty == 0:
        return "long"
    elif sell_qty > buy_qty:
        return "short"
    elif buy_qty > sell_qty:
        return "long"
    
    # Method 4: Check open_sell_qty vs open_buy_qty
    open_sell = _safe_int(position.get("open_sell_qty", 0))
    open_buy = _safe_int(position.get("open_buy_qty", 0))
    
    if open_sell > open_buy:
        return "short"
    elif open_buy > open_sell:
        return "long"
    
    # Method 5: Check quantity sign (some APIs use negative for short)
    qty = _safe_int(position.get("quantity", 0))
    if qty < 0:
        return "short"
    
    # Method 6: Check segment/product hints
    segment = str(position.get("segment", "")).lower()
    if "short" in segment:
        return "short"
    
    # Default fallback - LOG WARNING
    logger.warning(f"Could not determine position type for: {position}")
    logger.warning(f"Fields available: {list(position.keys())}")
    
    # Conservative default - assume long (safer for display)
    return "long"


def get_square_off_action(position_type: str) -> str:
    """
    Get the action needed to square off a position.
    
    - Long position → SELL to close
    - Short position → BUY to close
    """
    if position_type == "short":
        return "buy"
    else:
        return "sell"


def calculate_position_pnl(
    position_type: str,
    avg_price: float,
    ltp: float,
    quantity: int
) -> float:
    """
    Calculate P&L based on position type.
    
    Long Position:
        P&L = (Current Price - Avg Price) × Quantity
        Profit if price goes UP
        
    Short Position:
        P&L = (Avg Price - Current Price) × Quantity
        Profit if price goes DOWN
    """
    qty = abs(quantity)
    
    if position_type == "short":
        # Short: Sold at avg_price, current is ltp
        # Profit if ltp < avg_price (price dropped)
        pnl = (avg_price - ltp) * qty
    else:
        # Long: Bought at avg_price, current is ltp
        # Profit if ltp > avg_price (price increased)
        pnl = (ltp - avg_price) * qty
    
    return pnl


def _safe_int(value: Any) -> int:
    """Safely convert value to int."""
    if value is None:
        return 0
    try:
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value.lower() == "none":
                return 0
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _safe_float(value: Any) -> float:
    """Safely convert value to float."""
    if value is None:
        return 0.0
    try:
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value.lower() == "none":
                return 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# API RESPONSE HANDLER
# ══════════════════════════════════════════════════════════════════════════════


class APIResponse:
    """Wrapper for handling Breeze API responses consistently."""
    
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
        return {}
    
    @property
    def data(self) -> Dict[str, Any]:
        return self._data
    
    @property
    def data_list(self) -> List[Dict[str, Any]]:
        """Get data as list."""
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
        return []
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


# ══════════════════════════════════════════════════════════════════════════════
# STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════


class StateManager:
    """Centralized state management."""
    
    @staticmethod
    def init():
        SessionState.init_session_state()
        if "option_chain_cache" not in st.session_state:
            st.session_state.option_chain_cache = {}
        if "cache_timestamp" not in st.session_state:
            st.session_state.cache_timestamp = {}
        if "debug_mode" not in st.session_state:
            st.session_state.debug_mode = False
    
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
        st.session_state.option_chain_cache[key] = data
        st.session_state.cache_timestamp[key] = datetime.now()
    
    @staticmethod
    def get_cached_option_chain(key: str, ttl_seconds: int = 30) -> Optional[pd.DataFrame]:
        if key not in st.session_state.option_chain_cache:
            return None
        timestamp = st.session_state.cache_timestamp.get(key)
        if timestamp and (datetime.now() - timestamp).seconds < ttl_seconds:
            return st.session_state.option_chain_cache[key]
        return None


def handle_api_error(func):
    """Decorator for handling API errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error in {func.__name__}: {str(e)}")
            st.error(f"❌ An error occurred: {str(e)}")
            return None
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# UI COMPONENTS - HEADER & SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════


def render_header():
    st.markdown('<h1 class="main-header">📈 Breeze Options Trader</h1>', unsafe_allow_html=True)
    st.markdown("---")


def render_login_form():
    with st.form("login_form", clear_on_submit=False):
        st.subheader("🔐 API Credentials")
        
        api_key, api_secret, session_token = StateManager.get_credentials()
        
        new_api_key = st.text_input("API Key", value=api_key, type="password")
        new_api_secret = st.text_input("API Secret", value=api_secret, type="password")
        new_session_token = st.text_input("Session Token", value=session_token, type="password")
        
        st.markdown("""
        <div class="info-box">
            <strong>💡 Get Session Token:</strong><br>
            1. Login to ICICI Direct<br>
            2. Go to API section<br>
            3. Generate session token
        </div>
        """, unsafe_allow_html=True)
        
        submitted = st.form_submit_button("🔑 Connect", use_container_width=True)
        
        if submitted:
            if not all([new_api_key, new_api_secret, new_session_token]):
                st.warning("⚠️ Please fill all credentials")
                return
            
            with st.spinner("🔄 Connecting..."):
                client = BreezeClientWrapper(new_api_key, new_api_secret)
                result = client.connect(new_session_token)
                
                if result.get("success"):
                    StateManager.set_authenticated(True, client)
                    StateManager.set_credentials(new_api_key, new_api_secret, new_session_token)
                    st.success("✅ Connected!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ Failed: {result.get('message', 'Unknown error')}")


def render_authenticated_sidebar():
    client = StateManager.get_client()
    if not client:
        return
    
    st.markdown('<span class="status-badge status-connected">✅ Connected</span>', unsafe_allow_html=True)
    st.markdown("---")
    
    # User info
    st.subheader("👤 Account")
    try:
        customer_response = APIResponse(client.get_customer_details())
        if customer_response.success:
            name = customer_response.get("name", "User")
            st.markdown(f"**{name}**")
    except Exception:
        st.markdown("**User**")
    
    st.markdown(f"**{Utils.get_market_status()}**")
    st.markdown("---")
    
    # Funds
    st.subheader("💰 Funds")
    try:
        funds_response = APIResponse(client.get_funds())
        if funds_response.success:
            available = _safe_float(funds_response.get("available_margin", 0))
            used = _safe_float(funds_response.get("utilized_margin", 0))
            
            col1, col2 = st.columns(2)
            col1.metric("Available", Utils.format_currency(available))
            col2.metric("Used", Utils.format_currency(used))
    except Exception:
        st.info("Unable to fetch funds")
    
    st.markdown("---")
    
    if st.button("🔓 Disconnect", use_container_width=True):
        StateManager.set_authenticated(False, None)
        st.rerun()


def render_settings():
    st.subheader("⚙️ Settings")
    
    st.selectbox(
        "Default Instrument",
        options=list(Config.INSTRUMENTS.keys()),
        key="selected_instrument"
    )
    
    # Debug mode toggle
    debug_mode = st.checkbox("🔧 Debug Mode", value=st.session_state.get("debug_mode", False))
    st.session_state.debug_mode = debug_mode
    
    if debug_mode:
        st.caption("Debug mode shows raw API data")


def render_welcome_page():
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h2>Welcome to Breeze Options Trader</h2>
        <p style="color: #666;">Trade index options on ICICI Direct</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📊 Real-time Data\n- Option chain\n- Live quotes\n- OI Analysis")
    with col2:
        st.markdown("### 💰 Trading\n- Sell options\n- Square off\n- Order management")
    with col3:
        st.markdown("### 🛡️ Risk Mgmt\n- Margin calc\n- P&L tracking\n- Position monitoring")
    
    st.info("👈 **Login using the sidebar to start trading**")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_dashboard_tab():
    client = StateManager.get_client()
    if not client:
        return
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="dash_instrument")
    
    inst_config = Config.INSTRUMENTS[instrument]
    expiries = Config.get_next_expiries(instrument, 5)
    
    with col2:
        selected_expiry = st.selectbox("Expiry", expiries, format_func=Utils.format_expiry_date, key="dash_expiry")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", use_container_width=True)
    
    cache_key = f"{instrument}_{selected_expiry}"
    cached_df = None if refresh else StateManager.get_cached_option_chain(cache_key)
    
    if cached_df is not None:
        df = cached_df
        st.caption("📦 Cached data")
    else:
        with st.spinner("Loading..."):
            option_chain = client.get_option_chain(inst_config["stock_code"], inst_config["exchange"], selected_expiry)
        
        response = APIResponse(option_chain)
        if not response.success:
            st.error(f"Failed: {response.message}")
            return
        
        df = OptionChainAnalyzer.process_option_chain(option_chain.get("data", {}))
        if df.empty:
            st.warning("No data available")
            return
        
        StateManager.cache_option_chain(cache_key, df)
    
    st.subheader(f"📈 {instrument} Option Chain")
    
    col1, col2, col3, col4 = st.columns(4)
    pcr = OptionChainAnalyzer.calculate_pcr(df)
    max_pain = OptionChainAnalyzer.get_max_pain(df, inst_config["strike_gap"])
    
    col1.metric("PCR", f"{pcr:.2f}", delta="Bullish" if pcr > 1 else "Bearish")
    col2.metric("Max Pain", f"{max_pain:,}")
    
    if 'right' in df.columns:
        col3.metric("Call OI", f"{df[df['right']=='Call']['open_interest'].sum():,.0f}")
        col4.metric("Put OI", f"{df[df['right']=='Put']['open_interest'].sum():,.0f}")
    
    display_cols = ['strike_price', 'right', 'ltp', 'open_interest', 'volume', 'best_bid_price', 'best_offer_price']
    available_cols = [c for c in display_cols if c in df.columns]
    
    if available_cols:
        st.dataframe(df[available_cols], use_container_width=True, height=400, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# SELL OPTIONS TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_sell_options_tab():
    client = StateManager.get_client()
    if not client:
        return
    
    st.subheader("💰 Sell Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="sell_instrument")
        inst_config = Config.INSTRUMENTS[instrument]
        
        expiries = Config.get_next_expiries(instrument, 5)
        expiry = st.selectbox("Expiry", expiries, format_func=Utils.format_expiry_date, key="sell_expiry")
        
        option_type = st.radio("Option Type", ["CE (Call)", "PE (Put)"], horizontal=True, key="sell_opt_type")
        option_code = "CE" if "CE" in option_type else "PE"
        
        strike = st.number_input("Strike Price", min_value=0, step=inst_config["strike_gap"], key="sell_strike")
    
    with col2:
        lots = st.number_input("Lots", min_value=1, max_value=100, value=1, key="sell_lots")
        quantity = lots * inst_config["lot_size"]
        
        st.info(f"**Qty:** {quantity} ({lots} × {inst_config['lot_size']})")
        
        order_type = st.radio("Order Type", ["Market", "Limit"], horizontal=True, key="sell_order_type")
        limit_price = 0.0
        if order_type == "Limit":
            limit_price = st.number_input("Limit Price", min_value=0.0, step=0.05, key="sell_price")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 Get Quote", use_container_width=True, disabled=strike <= 0):
            with st.spinner("Fetching..."):
                quote = client.get_quotes(inst_config["stock_code"], inst_config["exchange"], expiry, strike, option_code)
                response = APIResponse(quote)
                if response.success:
                    qdata = response.data_list[0] if response.data_list else response.data
                    st.success(f"**LTP:** ₹{qdata.get('ltp', 'N/A')} | **Bid:** ₹{qdata.get('best_bid_price', 'N/A')} | **Ask:** ₹{qdata.get('best_offer_price', 'N/A')}")
                else:
                    st.error(response.message)
    
    with col2:
        if st.button("💰 Margin", use_container_width=True, disabled=strike <= 0):
            with st.spinner("Calculating..."):
                margin = client.get_margin_required(inst_config["stock_code"], inst_config["exchange"], expiry, strike, option_code, "sell", quantity)
                response = APIResponse(margin)
                if response.success:
                    st.info(f"**Required Margin:** ₹{response.get('required_margin', 'N/A')}")
                else:
                    st.warning("Could not calculate")
    
    st.markdown("""
    <div class="warning-box">
        <strong>⚠️ RISK WARNING:</strong> Option selling has <strong>UNLIMITED RISK</strong> potential.
    </div>
    """, unsafe_allow_html=True)
    
    confirm = st.checkbox("I understand the risks", key="sell_confirm")
    
    can_order = confirm and strike > 0 and (order_type == "Market" or limit_price > 0)
    
    if st.button(f"🔴 SELL {option_code}", type="primary", use_container_width=True, disabled=not can_order):
        with st.spinner("Placing order..."):
            fn = client.sell_call if option_code == "CE" else client.sell_put
            result = fn(inst_config["stock_code"], inst_config["exchange"], expiry, strike, quantity, order_type.lower(), limit_price)
            
            response = APIResponse(result)
            if response.success:
                st.success(f"✅ Order placed! ID: {response.get('order_id', 'N/A')}")
                st.balloons()
            else:
                st.error(f"❌ Failed: {response.message}")


# ══════════════════════════════════════════════════════════════════════════════
# SQUARE OFF TAB - FIXED POSITION TYPE DETECTION
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_square_off_tab():
    client = StateManager.get_client()
    if not client:
        return
    
    st.subheader("🔄 Square Off Positions")
    
    debug_mode = st.session_state.get("debug_mode", False)
    
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    
    response = APIResponse(positions)
    
    if not response.success:
        st.error(f"Failed: {response.message}")
        return
    
    position_list = response.data_list
    
    if not position_list:
        st.info("📭 No open positions")
        return
    
    # Filter option positions with non-zero quantity
    option_positions = []
    for p in position_list:
        product = str(p.get("product_type", "")).lower()
        qty = _safe_int(p.get("quantity", 0))
        
        if product == "options" and qty != 0:
            # CRITICAL: Determine position type correctly
            pos_type = get_position_type(p)
            p["_position_type"] = pos_type
            p["_quantity"] = abs(qty)
            option_positions.append(p)
    
    if not option_positions:
        st.info("📭 No open option positions")
        return
    
    st.success(f"Found **{len(option_positions)}** open position(s)")
    
    # Display positions with correct type
    display_data = []
    for p in option_positions:
        pos_type = p["_position_type"]
        qty = p["_quantity"]
        avg = _safe_float(p.get("average_price", 0))
        ltp = _safe_float(p.get("ltp", avg))
        
        # Calculate P&L correctly based on position type
        pnl = calculate_position_pnl(pos_type, avg, ltp, qty)
        
        # Action needed to square off
        sq_action = get_square_off_action(pos_type)
        
        display_data.append({
            "Instrument": p.get("stock_code", ""),
            "Strike": p.get("strike_price", ""),
            "Type": p.get("right", ""),
            "Expiry": p.get("expiry_date", ""),
            "Qty": qty,
            "Position": pos_type.upper(),
            "Avg": f"₹{avg:.2f}",
            "LTP": f"₹{ltp:.2f}",
            "P&L": f"₹{pnl:+,.2f}",
            "Action": sq_action.upper()
        })
    
    df = pd.DataFrame(display_data)
    
    # Style the dataframe
    def style_position(val):
        if val == "LONG":
            return "background-color: #d4edda; color: #155724; font-weight: bold"
        elif val == "SHORT":
            return "background-color: #f8d7da; color: #721c24; font-weight: bold"
        return ""
    
    def style_pnl(val):
        if isinstance(val, str) and val.startswith("₹"):
            if "+" in val:
                return "color: #28a745; font-weight: bold"
            elif "-" in val and not val.startswith("₹+"):
                return "color: #dc3545; font-weight: bold"
        return ""
    
    def style_action(val):
        if val == "BUY":
            return "background-color: #28a745; color: white; font-weight: bold"
        elif val == "SELL":
            return "background-color: #dc3545; color: white; font-weight: bold"
        return ""
    
    styled_df = df.style.applymap(style_position, subset=["Position"])
    styled_df = styled_df.applymap(style_pnl, subset=["P&L"])
    styled_df = styled_df.applymap(style_action, subset=["Action"])
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # Debug info
    if debug_mode:
        st.markdown("### 🔧 Debug: Raw Position Data")
        for i, p in enumerate(option_positions):
            with st.expander(f"Position {i+1}: {p.get('stock_code')} {p.get('strike_price')}"):
                st.json({k: v for k, v in p.items() if not k.startswith("_")})
    
    st.markdown("---")
    
    # Individual square off
    st.markdown("#### Square Off Individual Position")
    
    position_labels = []
    for i, p in enumerate(option_positions):
        pos_type = p["_position_type"]
        sq_action = get_square_off_action(pos_type)
        label = f"{p['stock_code']} {p['strike_price']} {p['right']} | {pos_type.upper()} | Qty: {p['_quantity']} | Action: {sq_action.upper()}"
        position_labels.append(label)
    
    selected_idx = st.selectbox("Select Position", range(len(position_labels)), format_func=lambda x: position_labels[x])
    
    selected_pos = option_positions[selected_idx]
    pos_type = selected_pos["_position_type"]
    qty = selected_pos["_quantity"]
    sq_action = get_square_off_action(pos_type)
    
    # Show clear info about what will happen
    if pos_type == "short":
        st.info(f"📌 This is a **SHORT** position. To close, we will **BUY** {qty} units.")
    else:
        st.info(f"📌 This is a **LONG** position. To close, we will **SELL** {qty} units.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        sq_order_type = st.radio("Order Type", ["Market", "Limit"], horizontal=True, key="sq_otype")
    
    with col2:
        sq_limit_price = 0.0
        if sq_order_type == "Limit":
            sq_limit_price = st.number_input("Limit Price", min_value=0.0, step=0.05, key="sq_price")
    
    sq_qty = st.slider("Quantity", min_value=1, max_value=qty, value=qty, key="sq_qty")
    
    # Button with correct action
    button_label = f"🔄 {sq_action.upper()} {sq_qty} to Close"
    button_color = "primary"
    
    if st.button(button_label, type=button_color, use_container_width=True):
        with st.spinner(f"Executing {sq_action.upper()} order..."):
            result = client.square_off_position(
                stock_code=selected_pos.get("stock_code"),
                exchange=selected_pos.get("exchange_code"),
                expiry_date=selected_pos.get("expiry_date"),
                strike_price=_safe_int(selected_pos.get("strike_price", 0)),
                option_type=str(selected_pos.get("right", "")).upper(),
                quantity=sq_qty,
                current_position=pos_type,  # Pass the correct position type
                order_type=sq_order_type.lower(),
                price=sq_limit_price
            )
            
            response = APIResponse(result)
            
            if response.success:
                st.success(f"✅ {sq_action.upper()} order executed successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ Failed: {response.message}")
    
    st.markdown("---")
    
    # Square off all
    st.markdown("#### ⚡ Square Off All")
    st.warning("⚠️ This will close ALL positions at market price!")
    
    confirm_all = st.checkbox("I confirm", key="sq_all_confirm")
    
    if st.button("🔴 SQUARE OFF ALL", disabled=not confirm_all, use_container_width=True):
        with st.spinner("Closing all positions..."):
            results = client.square_off_all()
            success = sum(1 for r in results if r.get("success"))
            fail = len(results) - success
            
            if success:
                st.success(f"✅ Closed {success} position(s)")
            if fail:
                st.warning(f"⚠️ Failed to close {fail} position(s)")
            
            time.sleep(1)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS TAB
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_orders_tab():
    client = StateManager.get_client()
    if not client:
        return
    
    st.subheader("📋 Orders")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        exchange = st.selectbox("Exchange", ["All", "NFO", "BFO"], key="ord_exch")
    with col2:
        from_date = st.date_input("From", datetime.now().date() - timedelta(days=7), key="ord_from")
    with col3:
        to_date = st.date_input("To", datetime.now().date(), key="ord_to")
    
    if st.button("🔄 Refresh Orders", use_container_width=True):
        st.rerun()
    
    with st.spinner("Loading..."):
        orders = client.get_order_list(
            "" if exchange == "All" else exchange,
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d")
        )
    
    response = APIResponse(orders)
    
    if not response.success:
        st.error(f"Failed: {response.message}")
        return
    
    order_list = response.data_list
    
    if not order_list:
        st.info("📭 No orders found")
        return
    
    df = pd.DataFrame(order_list)
    st.dataframe(df, use_container_width=True, height=400, hide_index=True)
    
    # Cancel pending orders
    pending = [o for o in order_list if str(o.get("order_status", "")).lower() in ["pending", "open"]]
    
    if pending:
        st.markdown("---")
        st.markdown("#### Cancel Pending Orders")
        
        labels = [f"{o.get('order_id')} | {o.get('stock_code')} {o.get('action')} {o.get('quantity')}" for o in pending]
        idx = st.selectbox("Select Order", range(len(labels)), format_func=lambda x: labels[x])
        
        if st.button("❌ Cancel Order", use_container_width=True):
            with st.spinner("Cancelling..."):
                result = client.cancel_order(pending[idx].get("order_id"), pending[idx].get("exchange_code"))
                response = APIResponse(result)
                if response.success:
                    st.success("✅ Cancelled!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"❌ Failed: {response.message}")


# ══════════════════════════════════════════════════════════════════════════════
# POSITIONS TAB - FIXED P&L CALCULATION
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def render_positions_tab():
    client = StateManager.get_client()
    if not client:
        return
    
    st.subheader("📍 Positions")
    
    debug_mode = st.session_state.get("debug_mode", False)
    
    if st.button("🔄 Refresh", use_container_width=True, key="pos_refresh"):
        st.rerun()
    
    with st.spinner("Loading..."):
        positions = client.get_portfolio_positions()
    
    response = APIResponse(positions)
    
    if not response.success:
        st.error(f"Failed: {response.message}")
        return
    
    position_list = response.data_list
    
    if not position_list:
        st.info("📭 No positions")
        return
    
    # Process positions with correct type detection
    total_pnl = 0.0
    enhanced = []
    
    for pos in position_list:
        qty = _safe_int(pos.get("quantity", 0))
        if qty == 0:
            continue
        
        # CRITICAL: Get correct position type
        pos_type = get_position_type(pos)
        
        avg = _safe_float(pos.get("average_price", 0))
        ltp = _safe_float(pos.get("ltp", avg))
        abs_qty = abs(qty)
        
        # Calculate P&L correctly
        pnl = calculate_position_pnl(pos_type, avg, ltp, abs_qty)
        total_pnl += pnl
        
        enhanced.append({
            "stock_code": pos.get("stock_code", ""),
            "exchange_code": pos.get("exchange_code", ""),
            "expiry_date": pos.get("expiry_date", ""),
            "strike_price": pos.get("strike_price", ""),
            "right": pos.get("right", ""),
            "quantity": abs_qty,
            "position_type": pos_type,
            "avg_price": avg,
            "ltp": ltp,
            "pnl": pnl,
            "_raw": pos  # Keep raw data for debug
        })
    
    if not enhanced:
        st.info("📭 No active positions")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total", len(enhanced))
    col2.metric("Long", sum(1 for p in enhanced if p["position_type"] == "long"))
    col3.metric("Short", sum(1 for p in enhanced if p["position_type"] == "short"))
    
    pnl_color = "normal" if total_pnl >= 0 else "inverse"
    col4.metric("Total P&L", f"₹{total_pnl:+,.2f}", delta_color=pnl_color)
    
    st.markdown("---")
    
    # Positions table
    display_data = []
    for p in enhanced:
        display_data.append({
            "Instrument": p["stock_code"],
            "Strike": p["strike_price"],
            "Type": p["right"],
            "Expiry": p["expiry_date"],
            "Qty": p["quantity"],
            "Position": p["position_type"].upper(),
            "Avg": f"₹{p['avg_price']:.2f}",
            "LTP": f"₹{p['ltp']:.2f}",
            "P&L": f"₹{p['pnl']:+,.2f}"
        })
    
    df = pd.DataFrame(display_data)
    
    # Style
    def style_pos(val):
        if val == "LONG":
            return "background-color: #d4edda; color: #155724; font-weight: bold"
        elif val == "SHORT":
            return "background-color: #f8d7da; color: #721c24; font-weight: bold"
        return ""
    
    def style_pnl(val):
        if isinstance(val, str):
            if "+" in val or (val.replace("₹", "").replace(",", "").replace(".", "").lstrip("-").isdigit() and not val.startswith("₹-")):
                num = float(val.replace("₹", "").replace(",", "").replace("+", ""))
                if num > 0:
                    return "color: #28a745; font-weight: bold"
            if "-" in val:
                return "color: #dc3545; font-weight: bold"
        return ""
    
    styled = df.style.applymap(style_pos, subset=["Position"])
    styled = styled.applymap(style_pnl, subset=["P&L"])
    
    st.dataframe(styled, use_container_width=True, hide_index=True)
    
    # Debug
    if debug_mode:
        st.markdown("---")
        st.markdown("### 🔧 Debug: Raw Position Data")
        for i, p in enumerate(enhanced):
            with st.expander(f"Position {i+1}: {p['stock_code']} {p['strike_price']}"):
                st.write(f"**Detected Type:** {p['position_type']}")
                st.write(f"**P&L Calculation:**")
                st.write(f"- Position: {p['position_type']}")
                st.write(f"- Avg Price: {p['avg_price']}")
                st.write(f"- LTP: {p['ltp']}")
                st.write(f"- Qty: {p['quantity']}")
                if p['position_type'] == 'short':
                    st.write(f"- Formula: (Avg - LTP) × Qty = ({p['avg_price']} - {p['ltp']}) × {p['quantity']} = {p['pnl']:.2f}")
                else:
                    st.write(f"- Formula: (LTP - Avg) × Qty = ({p['ltp']} - {p['avg_price']}) × {p['quantity']} = {p['pnl']:.2f}")
                st.json(p["_raw"])
    
    # Position details
    st.markdown("---")
    st.markdown("#### Position Details")
    
    for p in enhanced:
        emoji = "📈" if p["pnl"] >= 0 else "📉"
        pos_badge = "🟢 LONG" if p["position_type"] == "long" else "🔴 SHORT"
        
        with st.expander(f"{emoji} {p['stock_code']} {p['strike_price']} {p['right']} | {pos_badge} | P&L: ₹{p['pnl']:+,.2f}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Exchange:** {p['exchange_code']}")
                st.write(f"**Expiry:** {p['expiry_date']}")
                st.write(f"**Strike:** {p['strike_price']}")
            
            with col2:
                st.write(f"**Option:** {p['right']}")
                st.write(f"**Position:** {p['position_type'].upper()}")
                st.write(f"**Quantity:** {p['quantity']}")
            
            with col3:
                st.write(f"**Avg Price:** ₹{p['avg_price']:.2f}")
                st.write(f"**LTP:** ₹{p['ltp']:.2f}")
                pnl_text = f"₹{p['pnl']:+,.2f}"
                if p['pnl'] >= 0:
                    st.markdown(f"**P&L:** <span style='color:green'>{pnl_text}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"**P&L:** <span style='color:red'>{pnl_text}</span>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════


def render_main_dashboard():
    tabs = st.tabs(["📊 Dashboard", "💰 Sell Options", "🔄 Square Off", "📋 Orders", "📍 Positions"])
    
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
    StateManager.init()
    render_header()
    
    with st.sidebar:
        if not StateManager.is_authenticated():
            render_login_form()
        else:
            render_authenticated_sidebar()
        
        st.markdown("---")
        render_settings()
        
        st.markdown("---")
        st.caption("Breeze Options Trader v2.1")
    
    if not StateManager.is_authenticated():
        render_welcome_page()
    else:
        render_main_dashboard()


if __name__ == "__main__":
    main()
