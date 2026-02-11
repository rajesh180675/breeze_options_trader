"""
Breeze Options Trader - Main Application
Multi-page navigation with full functionality for every link.

Version: 3.0
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
# SETUP
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Breeze Options Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .main-header {
        font-size: 2.5rem; font-weight: bold;
        background: linear-gradient(90deg, #1f77b4, #2ecc71);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-align: center; padding: 1rem;
    }
    .page-header {
        font-size: 1.8rem; font-weight: bold; color: #1f77b4;
        border-bottom: 3px solid #1f77b4; padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    .status-connected { background: #d4edda; color: #155724;
        padding: 4px 12px; border-radius: 12px; font-weight: 600; }
    .status-disconnected { background: #f8d7da; color: #721c24;
        padding: 4px 12px; border-radius: 12px; font-weight: 600; }
    .nav-active {
        background: #1f77b4 !important; color: white !important;
        border-radius: 8px; font-weight: bold;
    }
    .profit { color: #28a745 !important; font-weight: bold; }
    .loss { color: #dc3545 !important; font-weight: bold; }
    .warning-box {
        background: #fff3cd; border-left: 4px solid #ffc107;
        padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0;
    }
    .info-box {
        background: #e7f3ff; border-left: 4px solid #2196F3;
        padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0;
    }
    .success-box {
        background: #d4edda; border-left: 4px solid #28a745;
        padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0;
    }
    .danger-box {
        background: #f8d7da; border-left: 4px solid #dc3545;
        padding: 1rem; margin: 1rem 0; border-radius: 0 8px 8px 0;
    }
    .metric-row { display: flex; gap: 1rem; margin: 1rem 0; }
    .stButton > button { width: 100%; }
    div[data-testid="stSidebar"] .stRadio > label { font-size: 1rem; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SAFE TYPE CONVERSION
# ══════════════════════════════════════════════════════════════════════════════


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        s = str(value).strip()
        if s == "" or s.lower() == "none":
            return 0
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        s = str(value).strip()
        if s == "" or s.lower() == "none":
            return 0.0
        return float(s)
    except (ValueError, TypeError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# POSITION TYPE DETECTION
# ══════════════════════════════════════════════════════════════════════════════


def get_position_type(position: Dict[str, Any]) -> str:
    """
    Determine LONG or SHORT from Breeze position data.

    Checks in priority order:
      1. action field  ("sell" → short, "buy" → long)
      2. position_type / segment hints
      3. sell_quantity vs buy_quantity
      4. open_sell_qty vs open_buy_qty
      5. quantity sign  (negative → short)
    """
    # 1. action
    action = str(position.get("action", "")).lower().strip()
    if action == "sell":
        return "short"
    if action == "buy":
        return "long"

    # 2. explicit type fields
    for field in ("position_type", "segment", "product"):
        val = str(position.get(field, "")).lower()
        if "short" in val or "sell" in val:
            return "short"
        if "long" in val or "buy" in val:
            return "long"

    # 3. sell vs buy quantity
    sell_qty = _safe_int(position.get("sell_quantity", 0))
    buy_qty = _safe_int(position.get("buy_quantity", 0))
    if sell_qty > 0 and buy_qty == 0:
        return "short"
    if buy_qty > 0 and sell_qty == 0:
        return "long"
    if sell_qty > buy_qty:
        return "short"
    if buy_qty > sell_qty:
        return "long"

    # 4. open qty
    open_sell = _safe_int(position.get("open_sell_qty", 0))
    open_buy = _safe_int(position.get("open_buy_qty", 0))
    if open_sell > open_buy:
        return "short"
    if open_buy > open_sell:
        return "long"

    # 5. negative quantity
    if _safe_int(position.get("quantity", 0)) < 0:
        return "short"

    logger.warning(f"Position type unknown for {position}")
    return "long"


def get_square_off_action(pos_type: str) -> str:
    """BUY to close short, SELL to close long."""
    return "buy" if pos_type == "short" else "sell"


def calculate_position_pnl(pos_type: str, avg: float, ltp: float, qty: int) -> float:
    qty = abs(qty)
    if pos_type == "short":
        return (avg - ltp) * qty
    return (ltp - avg) * qty


# ══════════════════════════════════════════════════════════════════════════════
# API RESPONSE WRAPPER
# ══════════════════════════════════════════════════════════════════════════════


class APIResponse:
    def __init__(self, response: Dict[str, Any]):
        self.raw = response
        self.success = response.get("success", False)
        self.message = response.get("message", "Unknown error")
        self._data = self._parse(response)

    def _parse(self, r: Dict) -> Dict:
        if not self.success:
            return {}
        data = r.get("data", {})
        if not isinstance(data, dict):
            return {}
        s = data.get("Success")
        if isinstance(s, dict):
            return s
        if isinstance(s, list) and s and isinstance(s[0], dict):
            return s[0]
        return {}

    @property
    def data(self) -> Dict:
        return self._data

    @property
    def data_list(self) -> List[Dict]:
        if not self.success:
            return []
        data = self.raw.get("data", {})
        if not isinstance(data, dict):
            return []
        s = data.get("Success")
        if isinstance(s, list):
            return s
        if isinstance(s, dict):
            return [s]
        return []

    def get(self, key: str, default: Any = None):
        return self._data.get(key, default)


# ══════════════════════════════════════════════════════════════════════════════
# STATE MANAGER
# ══════════════════════════════════════════════════════════════════════════════


class StateManager:
    @staticmethod
    def init():
        SessionState.init_session_state()
        for key, default in {
            "current_page": "Dashboard",
            "option_chain_cache": {},
            "cache_timestamp": {},
            "debug_mode": False,
        }.items():
            if key not in st.session_state:
                st.session_state[key] = default

    @staticmethod
    def is_authenticated() -> bool:
        return st.session_state.get("authenticated", False)

    @staticmethod
    def get_client() -> Optional[BreezeClientWrapper]:
        return st.session_state.get("breeze_client")

    @staticmethod
    def set_authenticated(val: bool, client=None):
        st.session_state.authenticated = val
        st.session_state.breeze_client = client

    @staticmethod
    def get_credentials() -> Tuple[str, str, str]:
        return (
            st.session_state.get("api_key", ""),
            st.session_state.get("api_secret", ""),
            st.session_state.get("session_token", ""),
        )

    @staticmethod
    def set_credentials(k, s, t):
        st.session_state.api_key = k
        st.session_state.api_secret = s
        st.session_state.session_token = t

    @staticmethod
    def cache_oc(key, df, ttl=30):
        st.session_state.option_chain_cache[key] = df
        st.session_state.cache_timestamp[key] = datetime.now()

    @staticmethod
    def get_cached_oc(key, ttl=30):
        if key not in st.session_state.option_chain_cache:
            return None
        ts = st.session_state.cache_timestamp.get(key)
        if ts and (datetime.now() - ts).seconds < ttl:
            return st.session_state.option_chain_cache[key]
        return None

    @staticmethod
    def set_page(page: str):
        st.session_state.current_page = page

    @staticmethod
    def get_page() -> str:
        return st.session_state.get("current_page", "Dashboard")


def handle_api_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            st.error(f"❌ Error: {e}")
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Navigation + Auth + Settings
# ══════════════════════════════════════════════════════════════════════════════


def render_sidebar():
    """Full sidebar: navigation, auth, settings."""
    with st.sidebar:
        st.markdown("## 📈 Breeze Trader")
        st.markdown("---")

        # ── Navigation ────────────────────────────────────────────────────
        st.markdown("### 🧭 Navigation")

        pages_unauthenticated = ["Dashboard"]
        pages_authenticated = [
            "Dashboard",
            "Option Chain",
            "Sell Options",
            "Square Off",
            "Orders",
            "Positions",
        ]

        available_pages = (
            pages_authenticated if StateManager.is_authenticated()
            else pages_unauthenticated
        )

        icons = {
            "Dashboard": "🏠",
            "Option Chain": "📊",
            "Sell Options": "💰",
            "Square Off": "🔄",
            "Orders": "📋",
            "Positions": "📍",
        }

        current = StateManager.get_page()
        if current not in available_pages:
            current = "Dashboard"

        selected = st.radio(
            "Go to",
            available_pages,
            index=available_pages.index(current),
            format_func=lambda p: f"{icons.get(p, '📄')} {p}",
            key="nav_radio",
            label_visibility="collapsed",
        )

        if selected != current:
            StateManager.set_page(selected)
            st.rerun()

        st.markdown("---")

        # ── Authentication ────────────────────────────────────────────────
        st.markdown("### 🔐 Authentication")

        if not StateManager.is_authenticated():
            _render_login_sidebar()
        else:
            _render_account_sidebar()

        st.markdown("---")

        # ── Settings ──────────────────────────────────────────────────────
        st.markdown("### ⚙️ Settings")

        st.selectbox(
            "Default Instrument",
            list(Config.INSTRUMENTS.keys()),
            key="selected_instrument",
        )

        debug = st.checkbox(
            "🔧 Debug Mode",
            value=st.session_state.get("debug_mode", False),
        )
        st.session_state.debug_mode = debug
        if debug:
            st.caption("Shows raw API data")

        st.markdown("---")
        st.caption("Breeze Options Trader v3.0")


def _render_login_sidebar():
    """Login form inside sidebar."""
    with st.form("login_form", clear_on_submit=False):
        api_key, api_secret, session_token = StateManager.get_credentials()

        new_key = st.text_input("API Key", value=api_key, type="password")
        new_secret = st.text_input("API Secret", value=api_secret, type="password")
        new_token = st.text_input("Session Token", value=session_token, type="password")

        st.markdown("""
        <div class="info-box">
        <b>💡 Get Session Token:</b><br>
        1. Login to <a href="https://www.icicidirect.com/" target="_blank">ICICI Direct</a><br>
        2. API section → Generate token
        </div>
        """, unsafe_allow_html=True)

        submitted = st.form_submit_button("🔑 Connect", use_container_width=True)

        if submitted:
            if not all([new_key, new_secret, new_token]):
                st.warning("⚠️ Fill all fields")
                return
            with st.spinner("Connecting..."):
                client = BreezeClientWrapper(new_key, new_secret)
                result = client.connect(new_token)
                if result.get("success"):
                    StateManager.set_authenticated(True, client)
                    StateManager.set_credentials(new_key, new_secret, new_token)
                    st.success("✅ Connected!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('message', 'Failed')}")


def _render_account_sidebar():
    """Account info + disconnect."""
    client = StateManager.get_client()
    if not client:
        return

    st.markdown(
        '<span class="status-connected">✅ Connected</span>',
        unsafe_allow_html=True,
    )

    try:
        r = APIResponse(client.get_customer_details())
        st.markdown(f"**👤 {r.get('name', 'User')}**")
    except Exception:
        st.markdown("**👤 User**")

    st.markdown(f"**{Utils.get_market_status()}**")

    try:
        r = APIResponse(client.get_funds())
        avail = _safe_float(r.get("available_margin", 0))
        used = _safe_float(r.get("utilized_margin", 0))
        c1, c2 = st.columns(2)
        c1.metric("Avail", Utils.format_currency(avail))
        c2.metric("Used", Utils.format_currency(used))
    except Exception:
        pass

    if st.button("🔓 Disconnect", use_container_width=True):
        StateManager.set_authenticated(False, None)
        StateManager.set_page("Dashboard")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD (Home)
# ══════════════════════════════════════════════════════════════════════════════


def page_dashboard():
    """Home / welcome page — shows overview when logged in, intro when not."""

    if not StateManager.is_authenticated():
        st.markdown(
            '<div class="page-header">🏠 Welcome</div>',
            unsafe_allow_html=True,
        )
        _render_welcome()
        return

    st.markdown(
        '<div class="page-header">🏠 Dashboard</div>',
        unsafe_allow_html=True,
    )

    client = StateManager.get_client()

    # ── Market Overview ───────────────────────────────────────────────────
    st.subheader("📈 Market Overview")
    st.markdown(f"**{Utils.get_market_status()}**")

    # ── Account Summary ───────────────────────────────────────────────────
    st.subheader("💰 Account Summary")

    try:
        funds = APIResponse(client.get_funds())
        avail = _safe_float(funds.get("available_margin", 0))
        used = _safe_float(funds.get("utilized_margin", 0))
        total = avail + used

        c1, c2, c3 = st.columns(3)
        c1.metric("Available Margin", Utils.format_currency(avail))
        c2.metric("Used Margin", Utils.format_currency(used))
        c3.metric("Total Margin", Utils.format_currency(total))

        if total > 0:
            pct = used / total
            st.progress(min(pct, 1.0))
            st.caption(f"Margin utilisation: {pct*100:.1f}%")
    except Exception:
        st.info("Unable to fetch funds")

    st.markdown("---")

    # ── Open Positions Summary ────────────────────────────────────────────
    st.subheader("📍 Open Positions Summary")

    try:
        pos = APIResponse(client.get_portfolio_positions())
        plist = pos.data_list

        active = [
            p for p in plist if _safe_int(p.get("quantity", 0)) != 0
        ]

        if not active:
            st.info("📭 No open positions")
        else:
            total_pnl = 0.0
            rows = []
            for p in active:
                pt = get_position_type(p)
                qty = abs(_safe_int(p.get("quantity", 0)))
                avg = _safe_float(p.get("average_price", 0))
                ltp = _safe_float(p.get("ltp", avg))
                pnl = calculate_position_pnl(pt, avg, ltp, qty)
                total_pnl += pnl
                rows.append({
                    "Instrument": p.get("stock_code", ""),
                    "Strike": p.get("strike_price", ""),
                    "Type": p.get("right", ""),
                    "Pos": pt.upper(),
                    "Qty": qty,
                    "P&L": f"₹{pnl:+,.2f}",
                })

            c1, c2, c3 = st.columns(3)
            c1.metric("Positions", len(rows))
            c2.metric(
                "Total P&L",
                f"₹{total_pnl:+,.2f}",
                delta_color="normal" if total_pnl >= 0 else "inverse",
            )
            c3.metric(
                "Short",
                sum(1 for r in rows if r["Pos"] == "SHORT"),
            )

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )
    except Exception as e:
        st.info(f"Unable to load positions: {e}")

    st.markdown("---")

    # ── Quick Actions ─────────────────────────────────────────────────────
    st.subheader("⚡ Quick Actions")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("📊 Option Chain", use_container_width=True):
            StateManager.set_page("Option Chain")
            st.rerun()
    with c2:
        if st.button("💰 Sell Options", use_container_width=True):
            StateManager.set_page("Sell Options")
            st.rerun()
    with c3:
        if st.button("🔄 Square Off", use_container_width=True):
            StateManager.set_page("Square Off")
            st.rerun()
    with c4:
        if st.button("📋 Orders", use_container_width=True):
            StateManager.set_page("Orders")
            st.rerun()


def _render_welcome():
    """Welcome page for unauthenticated users."""
    st.markdown("""
    <div style="text-align:center;padding:2rem">
    <h2>Trade Index Options on ICICI Direct</h2>
    <p style="color:#666">Powered by Breeze Connect SDK</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        ### 📊 Real-time Data
        - Live option chain
        - Real-time quotes
        - Open Interest analysis
        - Put-Call Ratio
        - Max Pain calculation
        """)
    with c2:
        st.markdown("""
        ### 💰 Trading
        - Sell Call options
        - Sell Put options
        - Quick square off
        - Position management
        - Order tracking
        """)
    with c3:
        st.markdown("""
        ### 🛡️ Risk Mgmt
        - Margin calculator
        - P&L tracking
        - Position monitoring
        - Risk warnings
        - Debug mode
        """)

    st.markdown("---")

    st.subheader("📈 Supported Instruments")
    st.dataframe(
        pd.DataFrame([
            {
                "Instrument": name,
                "Exchange": cfg["exchange"],
                "Lot Size": cfg["lot_size"],
                "Strike Gap": cfg["strike_gap"],
                "Expiry Day": Config.EXPIRY_DAYS.get(name, ""),
            }
            for name, cfg in Config.INSTRUMENTS.items()
        ]),
        use_container_width=True,
        hide_index=True,
    )

    st.info("👈 **Login using the sidebar to start trading**")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: OPTION CHAIN  (dedicated page, not merged with dashboard)
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def page_option_chain():
    st.markdown(
        '<div class="page-header">📊 Option Chain</div>',
        unsafe_allow_html=True,
    )

    client = StateManager.get_client()
    if not client:
        st.warning("Please connect first")
        return

    # ── Controls ──────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 1])

    with c1:
        instrument = st.selectbox(
            "Instrument",
            list(Config.INSTRUMENTS.keys()),
            key="oc_instrument",
        )
    inst = Config.INSTRUMENTS[instrument]
    expiries = Config.get_next_expiries(instrument, 5)

    with c2:
        expiry = st.selectbox(
            "Expiry",
            expiries,
            format_func=Utils.format_expiry_date,
            key="oc_expiry",
        )

    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", key="oc_refresh", use_container_width=True)

    # ── Filter ────────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        oc_filter = st.radio(
            "Show",
            ["All", "Calls Only", "Puts Only"],
            horizontal=True,
            key="oc_filter",
        )
    with c2:
        num_strikes = st.slider(
            "Strikes around ATM",
            min_value=5,
            max_value=30,
            value=15,
            key="oc_strikes",
        )

    # ── Fetch / Cache ─────────────────────────────────────────────────────
    cache_key = f"oc_{instrument}_{expiry}"
    cached = None if refresh else StateManager.get_cached_oc(cache_key)

    if cached is not None:
        df = cached
        st.caption("📦 Cached (auto-refreshes every 30 s)")
    else:
        with st.spinner("Loading option chain..."):
            raw = client.get_option_chain(
                inst["stock_code"], inst["exchange"], expiry,
            )
        r = APIResponse(raw)
        if not r.success:
            st.error(f"Failed: {r.message}")
            return
        df = OptionChainAnalyzer.process_option_chain(raw.get("data", {}))
        if df.empty:
            st.warning("No data")
            return
        StateManager.cache_oc(cache_key, df)

    # ── Metrics ───────────────────────────────────────────────────────────
    st.subheader(
        f"{instrument} — {Utils.format_expiry_date(expiry)}"
    )

    pcr = OptionChainAnalyzer.calculate_pcr(df)
    max_pain = OptionChainAnalyzer.get_max_pain(df, inst["strike_gap"])

    call_oi = (
        df[df["right"] == "Call"]["open_interest"].sum()
        if "right" in df.columns else 0
    )
    put_oi = (
        df[df["right"] == "Put"]["open_interest"].sum()
        if "right" in df.columns else 0
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PCR", f"{pcr:.2f}", delta="Bullish" if pcr > 1 else "Bearish")
    c2.metric("Max Pain", f"{max_pain:,}")
    c3.metric("Call OI", f"{call_oi:,.0f}")
    c4.metric("Put OI", f"{put_oi:,.0f}")

    st.markdown("---")

    # ── Apply filters ─────────────────────────────────────────────────────
    filtered = df.copy()

    if "right" in filtered.columns:
        if oc_filter == "Calls Only":
            filtered = filtered[filtered["right"] == "Call"]
        elif oc_filter == "Puts Only":
            filtered = filtered[filtered["right"] == "Put"]

    # Limit strikes around ATM
    if "strike_price" in filtered.columns and not filtered.empty:
        strikes_sorted = sorted(filtered["strike_price"].unique())
        if strikes_sorted:
            mid = len(strikes_sorted) // 2
            lo = max(0, mid - num_strikes)
            hi = min(len(strikes_sorted), mid + num_strikes + 1)
            keep = strikes_sorted[lo:hi]
            filtered = filtered[filtered["strike_price"].isin(keep)]

    # ── Display ───────────────────────────────────────────────────────────
    display_cols = [
        "strike_price", "right", "ltp", "open_interest", "volume",
        "best_bid_price", "best_offer_price", "ltp_percent_change",
    ]
    available = [c for c in display_cols if c in filtered.columns]

    rename_map = {
        "strike_price": "Strike",
        "right": "Type",
        "ltp": "LTP",
        "open_interest": "OI",
        "volume": "Volume",
        "best_bid_price": "Bid",
        "best_offer_price": "Ask",
        "ltp_percent_change": "Chg%",
    }

    if available:
        show = filtered[available].rename(columns=rename_map)
        st.dataframe(show, use_container_width=True, height=500, hide_index=True)
    else:
        st.dataframe(filtered, use_container_width=True, height=500)

    # ── OI Charts ─────────────────────────────────────────────────────────
    if "right" in filtered.columns and "strike_price" in filtered.columns and "open_interest" in filtered.columns:
        st.markdown("---")
        st.subheader("📊 Open Interest Distribution")

        calls = filtered[filtered["right"] == "Call"][["strike_price", "open_interest"]].rename(
            columns={"open_interest": "Call OI"})
        puts = filtered[filtered["right"] == "Put"][["strike_price", "open_interest"]].rename(
            columns={"open_interest": "Put OI"})

        merged = pd.merge(calls, puts, on="strike_price", how="outer").fillna(0)
        merged = merged.sort_values("strike_price")

        st.bar_chart(merged.set_index("strike_price"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SELL OPTIONS
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def page_sell_options():
    st.markdown(
        '<div class="page-header">💰 Sell Options</div>',
        unsafe_allow_html=True,
    )

    client = StateManager.get_client()
    if not client:
        st.warning("Please connect first")
        return

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### 📋 Contract")
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="sell_instr")
        inst = Config.INSTRUMENTS[instrument]
        expiry = st.selectbox(
            "Expiry",
            Config.get_next_expiries(instrument, 5),
            format_func=Utils.format_expiry_date,
            key="sell_exp",
        )
        opt = st.radio("Option", ["CE (Call)", "PE (Put)"], horizontal=True, key="sell_opt")
        opt_code = "CE" if "CE" in opt else "PE"
        strike = st.number_input(
            "Strike", min_value=0, step=inst["strike_gap"], key="sell_strike",
            help=f"Multiple of {inst['strike_gap']}",
        )
        if strike > 0 and strike % inst["strike_gap"] != 0:
            st.warning(f"⚠️ Should be multiple of {inst['strike_gap']}")

    with c2:
        st.markdown("#### 📝 Order")
        lots = st.number_input("Lots", 1, 100, 1, key="sell_lots")
        qty = lots * inst["lot_size"]
        st.info(f"**Qty:** {qty}  ({lots} × {inst['lot_size']})")
        otype = st.radio("Order Type", ["Market", "Limit"], horizontal=True, key="sell_otype")
        price = 0.0
        if otype == "Limit":
            price = st.number_input("Price ₹", min_value=0.0, step=0.05, key="sell_price")
            if price <= 0:
                st.warning("Enter a valid price")

    st.markdown("---")

    # ── Quote & Margin ────────────────────────────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        if st.button("📊 Get Quote", use_container_width=True, disabled=strike <= 0):
            with st.spinner("Fetching..."):
                q = APIResponse(client.get_quotes(
                    inst["stock_code"], inst["exchange"], expiry, strike, opt_code,
                ))
                if q.success:
                    d = q.data_list[0] if q.data_list else q.data
                    st.success(
                        f"**LTP:** ₹{d.get('ltp','N/A')} · "
                        f"**Bid:** ₹{d.get('best_bid_price','N/A')} · "
                        f"**Ask:** ₹{d.get('best_offer_price','N/A')}"
                    )
                else:
                    st.error(q.message)

    with c2:
        if st.button("💰 Margin", use_container_width=True, disabled=strike <= 0):
            with st.spinner("Calculating..."):
                m = APIResponse(client.get_margin_required(
                    inst["stock_code"], inst["exchange"], expiry, strike, opt_code, "sell", qty,
                ))
                if m.success:
                    st.info(f"**Required Margin:** ₹{m.get('required_margin','N/A')}")
                else:
                    st.warning("Could not calculate margin")

    st.markdown("---")

    # ── Risk warning & order ──────────────────────────────────────────────
    st.markdown("""
    <div class="danger-box">
    <b>⚠️ RISK WARNING:</b> Selling options carries <b>UNLIMITED RISK</b>.
    Ensure adequate margin.
    </div>
    """, unsafe_allow_html=True)

    confirm = st.checkbox("I understand the risks", key="sell_confirm")
    can_order = confirm and strike > 0 and strike % inst["strike_gap"] == 0 and (otype == "Market" or price > 0)

    if st.button(
        f"🔴 SELL {opt_code}",
        type="primary",
        use_container_width=True,
        disabled=not can_order,
    ):
        with st.spinner("Placing..."):
            fn = client.sell_call if opt_code == "CE" else client.sell_put
            r = APIResponse(fn(
                inst["stock_code"], inst["exchange"], expiry,
                strike, qty, otype.lower(), price,
            ))
            if r.success:
                st.markdown(f"""
                <div class="success-box">
                ✅ <b>Order Placed!</b><br>
                ID: {r.get('order_id','N/A')}<br>
                {instrument} {strike} {opt_code} × {qty}
                </div>
                """, unsafe_allow_html=True)
                st.balloons()
            else:
                st.error(f"❌ {r.message}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SQUARE OFF
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def page_square_off():
    st.markdown(
        '<div class="page-header">🔄 Square Off</div>',
        unsafe_allow_html=True,
    )

    client = StateManager.get_client()
    if not client:
        st.warning("Please connect first")
        return

    debug = st.session_state.get("debug_mode", False)

    with st.spinner("Loading positions..."):
        positions = APIResponse(client.get_portfolio_positions())

    if not positions.success:
        st.error(f"Failed: {positions.message}")
        return

    # Build list of open option positions
    option_positions = []
    for p in positions.data_list:
        if str(p.get("product_type", "")).lower() != "options":
            continue
        qty = _safe_int(p.get("quantity", 0))
        if qty == 0:
            continue
        pt = get_position_type(p)
        p["_type"] = pt
        p["_qty"] = abs(qty)
        p["_action"] = get_square_off_action(pt)
        avg = _safe_float(p.get("average_price", 0))
        ltp = _safe_float(p.get("ltp", avg))
        p["_pnl"] = calculate_position_pnl(pt, avg, ltp, abs(qty))
        option_positions.append(p)

    if not option_positions:
        st.info("📭 No open option positions")
        return

    st.success(f"**{len(option_positions)}** open position(s)")

    # ── Table ─────────────────────────────────────────────────────────────
    rows = []
    for p in option_positions:
        rows.append({
            "Instrument": p.get("stock_code", ""),
            "Strike": p.get("strike_price", ""),
            "Option": p.get("right", ""),
            "Expiry": p.get("expiry_date", ""),
            "Qty": p["_qty"],
            "Position": p["_type"].upper(),
            "Avg": f"₹{_safe_float(p.get('average_price',0)):.2f}",
            "LTP": f"₹{_safe_float(p.get('ltp',0)):.2f}",
            "P&L": f"₹{p['_pnl']:+,.2f}",
            "To Close": p["_action"].upper(),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if debug:
        with st.expander("🔧 Raw Position Data"):
            for i, p in enumerate(option_positions):
                st.write(f"**Position {i+1}:**")
                st.json({k: v for k, v in p.items() if not k.startswith("_")})

    st.markdown("---")

    # ── Individual Square Off ─────────────────────────────────────────────
    st.subheader("Square Off Individual")

    labels = [
        f"{p.get('stock_code')} {p.get('strike_price')} {p.get('right')} "
        f"| {p['_type'].upper()} | Qty:{p['_qty']} | Action:{p['_action'].upper()}"
        for p in option_positions
    ]

    idx = st.selectbox("Select Position", range(len(labels)), format_func=lambda x: labels[x])
    sel = option_positions[idx]

    # Info banner
    if sel["_type"] == "short":
        st.markdown("""
        <div class="info-box">
        📌 <b>SHORT position</b> — will place a <b>BUY</b> order to close.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="info-box">
        📌 <b>LONG position</b> — will place a <b>SELL</b> order to close.
        </div>
        """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        sq_otype = st.radio("Order", ["Market", "Limit"], horizontal=True, key="sq_otype")
    with c2:
        sq_price = 0.0
        if sq_otype == "Limit":
            sq_price = st.number_input("Price", min_value=0.0, step=0.05, key="sq_price")

    sq_qty = st.slider("Qty to close", 1, sel["_qty"], sel["_qty"], key="sq_qty")

    action = sel["_action"]
    btn_text = f"🔄 {action.upper()} {sq_qty} to Close {sel['_type'].upper()}"

    if st.button(btn_text, type="primary", use_container_width=True):
        with st.spinner(f"Executing {action.upper()}..."):
            result = APIResponse(client.square_off_position(
                stock_code=sel.get("stock_code"),
                exchange=sel.get("exchange_code"),
                expiry_date=sel.get("expiry_date"),
                strike_price=_safe_int(sel.get("strike_price", 0)),
                option_type=str(sel.get("right", "")).upper(),
                quantity=sq_qty,
                current_position=sel["_type"],
                order_type=sq_otype.lower(),
                price=sq_price,
            ))
            if result.success:
                st.success(f"✅ {action.upper()} order placed!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ {result.message}")

    st.markdown("---")

    # ── Square Off All ────────────────────────────────────────────────────
    st.subheader("⚡ Square Off ALL")
    st.markdown("""
    <div class="danger-box">
    ⚠️ Closes <b>ALL</b> open option positions at <b>market price</b>.
    </div>
    """, unsafe_allow_html=True)

    confirm = st.checkbox("I confirm", key="sq_all_confirm")
    if st.button("🔴 SQUARE OFF ALL", disabled=not confirm, use_container_width=True):
        with st.spinner("Closing all..."):
            results = client.square_off_all()
            ok = sum(1 for r in results if r.get("success"))
            fail = len(results) - ok
            if ok:
                st.success(f"✅ Closed {ok} position(s)")
            if fail:
                st.warning(f"⚠️ Failed: {fail}")
            time.sleep(1)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ORDERS
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def page_orders():
    st.markdown(
        '<div class="page-header">📋 Orders</div>',
        unsafe_allow_html=True,
    )

    client = StateManager.get_client()
    if not client:
        st.warning("Please connect first")
        return

    # ── Filters ───────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        exch = st.selectbox("Exchange", ["All", "NFO", "BFO"], key="ord_exch")
    with c2:
        fd = st.date_input("From", datetime.now().date() - timedelta(days=7), key="ord_from")
    with c3:
        td = st.date_input("To", datetime.now().date(), key="ord_to")

    if st.button("🔄 Refresh Orders", use_container_width=True):
        st.rerun()

    # ── Fetch ─────────────────────────────────────────────────────────────
    with st.spinner("Loading..."):
        orders = APIResponse(client.get_order_list(
            "" if exch == "All" else exch,
            fd.strftime("%Y-%m-%d"),
            td.strftime("%Y-%m-%d"),
        ))

    if not orders.success:
        st.error(f"Failed: {orders.message}")
        return

    olist = orders.data_list
    if not olist:
        st.info("📭 No orders found")
        return

    # ── Summary ───────────────────────────────────────────────────────────
    total = len(olist)
    executed = sum(1 for o in olist if str(o.get("order_status", "")).lower() == "executed")
    pending = sum(1 for o in olist if str(o.get("order_status", "")).lower() in ("pending", "open"))
    rejected = sum(1 for o in olist if str(o.get("order_status", "")).lower() == "rejected")
    cancelled = sum(1 for o in olist if str(o.get("order_status", "")).lower() == "cancelled")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total", total)
    c2.metric("Executed", executed)
    c3.metric("Pending", pending)
    c4.metric("Rejected", rejected)
    c5.metric("Cancelled", cancelled)

    st.markdown("---")

    # ── Table ─────────────────────────────────────────────────────────────
    df = pd.DataFrame(olist)
    show_cols = [
        "order_id", "stock_code", "action", "quantity", "price",
        "order_type", "order_status", "order_datetime", "strike_price", "right",
    ]
    avail = [c for c in show_cols if c in df.columns]
    rename = {
        "order_id": "ID", "stock_code": "Instrument", "action": "Action",
        "quantity": "Qty", "price": "Price", "order_type": "Type",
        "order_status": "Status", "order_datetime": "Time",
        "strike_price": "Strike", "right": "Option",
    }
    if avail:
        st.dataframe(df[avail].rename(columns=rename), use_container_width=True, height=400, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, height=400)

    # ── Manage Pending ────────────────────────────────────────────────────
    pending_orders = [
        o for o in olist
        if str(o.get("order_status", "")).lower() in ("pending", "open")
    ]

    if pending_orders:
        st.markdown("---")
        st.subheader("⚙️ Manage Pending Orders")

        labels = [
            f"{o.get('order_id','?')} | {o.get('stock_code','')} "
            f"{o.get('action','')} {o.get('quantity','')}"
            for o in pending_orders
        ]
        pidx = st.selectbox("Select", range(len(labels)), format_func=lambda x: labels[x])
        sel = pending_orders[pidx]

        c1, c2 = st.columns(2)
        with c1:
            if st.button("❌ Cancel", use_container_width=True):
                with st.spinner("Cancelling..."):
                    r = APIResponse(client.cancel_order(
                        sel.get("order_id"), sel.get("exchange_code"),
                    ))
                    if r.success:
                        st.success("✅ Cancelled")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ {r.message}")

        with c2:
            with st.expander("✏️ Modify"):
                new_p = st.number_input(
                    "New Price", min_value=0.0,
                    value=_safe_float(sel.get("price", 0)), step=0.05,
                )
                new_q = st.number_input(
                    "New Qty", min_value=1,
                    value=_safe_int(sel.get("quantity", 1)),
                )
                if st.button("💾 Save", use_container_width=True):
                    with st.spinner("Modifying..."):
                        r = APIResponse(client.modify_order(
                            sel.get("order_id"), sel.get("exchange_code"),
                            new_q, new_p,
                        ))
                        if r.success:
                            st.success("✅ Modified")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {r.message}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: POSITIONS
# ══════════════════════════════════════════════════════════════════════════════


@handle_api_error
def page_positions():
    st.markdown(
        '<div class="page-header">📍 Positions</div>',
        unsafe_allow_html=True,
    )

    client = StateManager.get_client()
    if not client:
        st.warning("Please connect first")
        return

    debug = st.session_state.get("debug_mode", False)

    if st.button("🔄 Refresh", use_container_width=True, key="pos_ref"):
        st.rerun()

    with st.spinner("Loading..."):
        positions = APIResponse(client.get_portfolio_positions())

    if not positions.success:
        st.error(f"Failed: {positions.message}")
        return

    plist = positions.data_list
    if not plist:
        st.info("📭 No positions")
        return

    # ── Process ───────────────────────────────────────────────────────────
    enhanced = []
    total_pnl = 0.0

    for p in plist:
        qty = _safe_int(p.get("quantity", 0))
        if qty == 0:
            continue

        pt = get_position_type(p)
        abs_qty = abs(qty)
        avg = _safe_float(p.get("average_price", 0))
        ltp = _safe_float(p.get("ltp", avg))
        pnl = calculate_position_pnl(pt, avg, ltp, abs_qty)
        total_pnl += pnl

        enhanced.append({
            "stock_code": p.get("stock_code", ""),
            "exchange": p.get("exchange_code", ""),
            "expiry": p.get("expiry_date", ""),
            "strike": p.get("strike_price", ""),
            "right": p.get("right", ""),
            "qty": abs_qty,
            "type": pt,
            "avg": avg,
            "ltp": ltp,
            "pnl": pnl,
            "_raw": p,
        })

    if not enhanced:
        st.info("📭 No active positions")
        return

    # ── Summary ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(enhanced))
    c2.metric("Long", sum(1 for e in enhanced if e["type"] == "long"))
    c3.metric("Short", sum(1 for e in enhanced if e["type"] == "short"))
    c4.metric(
        "P&L",
        f"₹{total_pnl:+,.2f}",
        delta_color="normal" if total_pnl >= 0 else "inverse",
    )

    st.markdown("---")

    # ── Table ─────────────────────────────────────────────────────────────
    rows = []
    for e in enhanced:
        rows.append({
            "Instrument": e["stock_code"],
            "Strike": e["strike"],
            "Option": e["right"],
            "Expiry": e["expiry"],
            "Qty": e["qty"],
            "Position": e["type"].upper(),
            "Avg": f"₹{e['avg']:.2f}",
            "LTP": f"₹{e['ltp']:.2f}",
            "P&L": f"₹{e['pnl']:+,.2f}",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Debug ─────────────────────────────────────────────────────────────
    if debug:
        st.markdown("---")
        st.subheader("🔧 Debug: Raw Data")
        for i, e in enumerate(enhanced):
            with st.expander(f"Pos {i+1}: {e['stock_code']} {e['strike']}"):
                st.write(f"**Detected:** {e['type'].upper()}")
                if e["type"] == "short":
                    st.code(f"P&L = (Avg - LTP) × Qty = ({e['avg']} - {e['ltp']}) × {e['qty']} = {e['pnl']:.2f}")
                else:
                    st.code(f"P&L = (LTP - Avg) × Qty = ({e['ltp']} - {e['avg']}) × {e['qty']} = {e['pnl']:.2f}")
                st.json(e["_raw"])

    st.markdown("---")

    # ── Details ───────────────────────────────────────────────────────────
    st.subheader("📊 Position Details")

    for e in enhanced:
        emoji = "📈" if e["pnl"] >= 0 else "📉"
        badge = "🟢 LONG" if e["type"] == "long" else "🔴 SHORT"
        action = get_square_off_action(e["type"])

        with st.expander(
            f"{emoji} {e['stock_code']} {e['strike']} {e['right']} "
            f"| {badge} | P&L: ₹{e['pnl']:+,.2f}"
        ):
            c1, c2, c3 = st.columns(3)

            with c1:
                st.markdown("**Contract**")
                st.write(f"Exchange: {e['exchange']}")
                st.write(f"Expiry: {e['expiry']}")
                st.write(f"Strike: {e['strike']}")
                st.write(f"Option: {e['right']}")

            with c2:
                st.markdown("**Position**")
                st.write(f"Direction: **{e['type'].upper()}**")
                st.write(f"Quantity: {e['qty']}")
                st.write(f"Avg Price: ₹{e['avg']:.2f}")
                st.write(f"LTP: ₹{e['ltp']:.2f}")

            with c3:
                st.markdown("**P&L**")
                if e["pnl"] >= 0:
                    st.markdown(f"<span class='profit'>₹{e['pnl']:+,.2f}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span class='loss'>₹{e['pnl']:+,.2f}</span>", unsafe_allow_html=True)

                if e["avg"] > 0:
                    pct = (e["pnl"] / (e["avg"] * e["qty"])) * 100
                    st.write(f"Return: {pct:+.2f}%")

                st.write(f"To close: **{action.upper()}**")

            # Quick square-off button inside details
            if st.button(
                f"🔄 {action.upper()} to Close",
                key=f"quick_sq_{e['stock_code']}_{e['strike']}_{e['right']}",
                use_container_width=True,
            ):
                StateManager.set_page("Square Off")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER — maps page name → function
# ══════════════════════════════════════════════════════════════════════════════


PAGE_MAP = {
    "Dashboard": page_dashboard,
    "Option Chain": page_option_chain,
    "Sell Options": page_sell_options,
    "Square Off": page_square_off,
    "Orders": page_orders,
    "Positions": page_positions,
}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════


def main():
    StateManager.init()

    # Sidebar (navigation + auth + settings)
    render_sidebar()

    # Header
    st.markdown(
        '<h1 class="main-header">📈 Breeze Options Trader</h1>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Route to current page
    current_page = StateManager.get_page()
    page_fn = PAGE_MAP.get(current_page, page_dashboard)

    # Guard authenticated pages
    auth_required = {"Option Chain", "Sell Options", "Square Off", "Orders", "Positions"}

    if current_page in auth_required and not StateManager.is_authenticated():
        st.warning("🔒 Please login to access this page")
        st.info("👈 Enter your credentials in the sidebar")
        return

    page_fn()


if __name__ == "__main__":
    main()
