"""
Breeze Options Trader — Main Application.
══════════════════════════════════════════
Multi-page navigation with every page fully functional.

FIXES in v3.2:
  • SENSEX uses stock_code BSESEN
  • NIFTY expires Tuesday, SENSEX expires Thursday
  • Orders & Trades page fully working with proper date handling
  • Position type detection from action/sell_qty/buy_qty fields
  • P&L calculated correctly for long AND short
  • All navigation links route to dedicated pages
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
# LOGGING & PAGE CONFIG
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
# CSS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
.main-header {
    font-size:2.5rem; font-weight:bold;
    background:linear-gradient(90deg,#1f77b4,#2ecc71);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    text-align:center; padding:1rem;
}
.page-header {
    font-size:1.8rem; font-weight:bold; color:#1f77b4;
    border-bottom:3px solid #1f77b4; padding-bottom:.5rem; margin-bottom:1rem;
}
.status-connected {
    background:#d4edda; color:#155724;
    padding:4px 12px; border-radius:12px; font-weight:600;
}
.profit  { color:#28a745!important; font-weight:bold; }
.loss    { color:#dc3545!important; font-weight:bold; }
.warning-box {
    background:#fff3cd; border-left:4px solid #ffc107;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0;
}
.info-box {
    background:#e7f3ff; border-left:4px solid #2196F3;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0;
}
.success-box {
    background:#d4edda; border-left:4px solid #28a745;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0;
}
.danger-box {
    background:#f8d7da; border-left:4px solid #dc3545;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0;
}
.stButton>button { width:100%; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SAFE TYPE CONVERTERS
# ══════════════════════════════════════════════════════════════════════════════

def safe_int(v: Any) -> int:
    """Convert anything to int without crashing."""
    if v is None:
        return 0
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return 0


def safe_float(v: Any) -> float:
    """Convert anything to float without crashing."""
    if v is None:
        return 0.0
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# POSITION TYPE DETECTION  — CRITICAL FOR SQUARE-OFF
# ══════════════════════════════════════════════════════════════════════════════

def detect_position_type(pos: Dict[str, Any]) -> str:
    """
    Determine if position is LONG or SHORT.

    Breeze API returns POSITIVE quantity for BOTH long and short.
    We check multiple fields in priority order:
      1.  action field           "sell" → short
      2.  sell_quantity vs buy_quantity
      3.  open_sell_qty vs open_buy_qty
      4.  quantity sign          negative → short
    """
    # 1. action
    action = str(pos.get("action", "")).lower().strip()
    if action == "sell":
        return "short"
    if action == "buy":
        return "long"

    # 2. explicit type fields
    for fld in ("position_type", "segment", "product"):
        val = str(pos.get(fld, "")).lower()
        if "short" in val or "sell" in val:
            return "short"
        if "long" in val or "buy" in val:
            return "long"

    # 3. sell vs buy quantity
    sq = safe_int(pos.get("sell_quantity", 0))
    bq = safe_int(pos.get("buy_quantity", 0))
    if sq > 0 and bq == 0:
        return "short"
    if bq > 0 and sq == 0:
        return "long"
    if sq > bq:
        return "short"
    if bq > sq:
        return "long"

    # 4. open qty
    osq = safe_int(pos.get("open_sell_qty", 0))
    obq = safe_int(pos.get("open_buy_qty", 0))
    if osq > obq:
        return "short"
    if obq > osq:
        return "long"

    # 5. negative quantity
    if safe_int(pos.get("quantity", 0)) < 0:
        return "short"

    logger.warning(f"Cannot determine position type, defaulting long: {pos}")
    return "long"


def close_action(pos_type: str) -> str:
    """Action required to close a position."""
    return "buy" if pos_type == "short" else "sell"


def calc_pnl(pos_type: str, avg: float, ltp: float, qty: int) -> float:
    """
    Long  P&L = (LTP − Avg) × Qty   → profit when price rises
    Short P&L = (Avg − LTP) × Qty   → profit when price falls
    """
    q = abs(qty)
    if pos_type == "short":
        return (avg - ltp) * q
    return (ltp - avg) * q


# ══════════════════════════════════════════════════════════════════════════════
# API RESPONSE WRAPPER
# ══════════════════════════════════════════════════════════════════════════════

class APIResp:
    """
    Breeze returns Success as dict OR list inconsistently.
    This wrapper normalises both cases.
    """

    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.ok = raw.get("success", False)
        self.msg = raw.get("message", "Unknown error")
        self._single = self._extract_single(raw)

    def _extract_single(self, r: Dict) -> Dict:
        if not self.ok:
            return {}
        d = r.get("data", {})
        if not isinstance(d, dict):
            return {}
        s = d.get("Success")
        if isinstance(s, dict):
            return s
        if isinstance(s, list) and s and isinstance(s[0], dict):
            return s[0]
        return {}

    @property
    def data(self) -> Dict[str, Any]:
        """First item as dict."""
        return self._single

    @property
    def items(self) -> List[Dict[str, Any]]:
        """All items as list."""
        if not self.ok:
            return []
        d = self.raw.get("data", {})
        if not isinstance(d, dict):
            return []
        s = d.get("Success")
        if isinstance(s, list):
            return s
        if isinstance(s, dict):
            return [s]
        return []

    def get(self, key: str, default: Any = None):
        return self._single.get(key, default)


# ══════════════════════════════════════════════════════════════════════════════
# STATE MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class State:
    """Centralised session state access."""

    @staticmethod
    def init():
        SessionState.init_session_state()

    @staticmethod
    def authed() -> bool:
        return st.session_state.get("authenticated", False)

    @staticmethod
    def client() -> Optional[BreezeClientWrapper]:
        return st.session_state.get("breeze_client")

    @staticmethod
    def set_auth(val: bool, client=None):
        st.session_state.authenticated = val
        st.session_state.breeze_client = client

    @staticmethod
    def creds() -> Tuple[str, str, str]:
        return (
            st.session_state.get("api_key", ""),
            st.session_state.get("api_secret", ""),
            st.session_state.get("session_token", ""),
        )

    @staticmethod
    def set_creds(k, s, t):
        st.session_state.api_key = k
        st.session_state.api_secret = s
        st.session_state.session_token = t

    @staticmethod
    def page() -> str:
        return st.session_state.get("current_page", "Dashboard")

    @staticmethod
    def go(page: str):
        st.session_state.current_page = page

    @staticmethod
    def cache_oc(key: str, df: pd.DataFrame):
        st.session_state.option_chain_cache[key] = df
        st.session_state.cache_timestamp[key] = datetime.now()

    @staticmethod
    def get_oc_cache(key: str, ttl: int = 30) -> Optional[pd.DataFrame]:
        cache = st.session_state.get("option_chain_cache", {})
        if key not in cache:
            return None
        ts = st.session_state.get("cache_timestamp", {}).get(key)
        if ts and (datetime.now() - ts).seconds < ttl:
            return cache[key]
        return None


def api_guard(fn):
    """Decorator: catch exceptions, show error toast."""
    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            logger.error(f"{fn.__name__}: {e}")
            st.error(f"❌ {e}")
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

ALL_PAGES = [
    "Dashboard", "Option Chain", "Sell Options",
    "Square Off", "Orders & Trades", "Positions",
]
PAGE_ICONS = {
    "Dashboard": "🏠", "Option Chain": "📊", "Sell Options": "💰",
    "Square Off": "🔄", "Orders & Trades": "📋", "Positions": "📍",
}


def render_sidebar():
    with st.sidebar:
        st.markdown("## 📈 Breeze Trader")
        st.markdown("---")

        # ── Navigation ────────────────────────────────────────────────
        available = ALL_PAGES if State.authed() else ["Dashboard"]
        cur = State.page()
        if cur not in available:
            cur = "Dashboard"

        sel = st.radio(
            "Navigation",
            available,
            index=available.index(cur),
            format_func=lambda p: f"{PAGE_ICONS.get(p, '📄')} {p}",
            label_visibility="collapsed",
        )
        if sel != cur:
            State.go(sel)
            st.rerun()

        st.markdown("---")

        # ── Auth ──────────────────────────────────────────────────────
        if not State.authed():
            _sidebar_login()
        else:
            _sidebar_account()

        st.markdown("---")

        # ── Settings ──────────────────────────────────────────────────
        st.markdown("### ⚙️ Settings")
        st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()),
                     key="selected_instrument")
        st.session_state.debug_mode = st.checkbox(
            "🔧 Debug", value=st.session_state.get("debug_mode", False))
        st.caption("v3.2")


def _sidebar_login():
    with st.form("login", clear_on_submit=False):
        st.markdown("### 🔐 Login")
        k, s, t = State.creds()
        nk = st.text_input("API Key", value=k, type="password")
        ns = st.text_input("API Secret", value=s, type="password")
        nt = st.text_input("Session Token", value=t, type="password")
        st.caption("Get token from ICICI Direct → API section")

        if st.form_submit_button("🔑 Connect", use_container_width=True):
            if not all([nk, ns, nt]):
                st.warning("Fill all fields")
                return
            with st.spinner("Connecting..."):
                c = BreezeClientWrapper(nk, ns)
                r = c.connect(nt)
                if r["success"]:
                    State.set_auth(True, c)
                    State.set_creds(nk, ns, nt)
                    st.success("✅ Connected!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ {r['message']}")


def _sidebar_account():
    cl = State.client()
    if not cl:
        return

    st.markdown('<span class="status-connected">✅ Connected</span>',
                unsafe_allow_html=True)
    try:
        r = APIResp(cl.get_customer_details())
        st.markdown(f"**👤 {r.get('name', 'User')}**")
    except Exception:
        pass

    st.markdown(f"**{Utils.get_market_status()}**")

    try:
        r = APIResp(cl.get_funds())
        avail = safe_float(r.get("available_margin", 0))
        st.metric("Margin", Utils.format_currency(avail))
    except Exception:
        pass

    if st.button("🔓 Disconnect", use_container_width=True):
        State.set_auth(False)
        State.go("Dashboard")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.markdown('<div class="page-header">🏠 Dashboard</div>',
                unsafe_allow_html=True)

    if not State.authed():
        _welcome()
        return

    cl = State.client()

    # ── Account ───────────────────────────────────────────────────────
    st.subheader(f"📈 {Utils.get_market_status()}")
    try:
        f = APIResp(cl.get_funds())
        av = safe_float(f.get("available_margin", 0))
        us = safe_float(f.get("utilized_margin", 0))
        c1, c2, c3 = st.columns(3)
        c1.metric("Available", Utils.format_currency(av))
        c2.metric("Used", Utils.format_currency(us))
        c3.metric("Total", Utils.format_currency(av + us))
    except Exception:
        pass

    st.markdown("---")

    # ── Positions ─────────────────────────────────────────────────────
    st.subheader("📍 Open Positions")
    try:
        pos = APIResp(cl.get_portfolio_positions())
        active = [p for p in pos.items if safe_int(p.get("quantity", 0)) != 0]
        if not active:
            st.info("📭 No open positions")
        else:
            total_pnl = 0.0
            rows = []
            for p in active:
                pt = detect_position_type(p)
                q = abs(safe_int(p.get("quantity", 0)))
                avg = safe_float(p.get("average_price", 0))
                ltp = safe_float(p.get("ltp", avg))
                pnl = calc_pnl(pt, avg, ltp, q)
                total_pnl += pnl
                disp_name = Config.get_instrument_display(p.get("stock_code", ""))
                rows.append({
                    "Instrument": disp_name,
                    "Strike": p.get("strike_price", ""),
                    "Type": p.get("right", ""),
                    "Position": pt.upper(),
                    "Qty": q,
                    "P&L": f"₹{pnl:+,.2f}",
                })
            c1, c2 = st.columns([3, 1])
            c1.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            c2.metric("Total P&L", f"₹{total_pnl:+,.2f}",
                       delta_color="normal" if total_pnl >= 0 else "inverse")
    except Exception as e:
        st.warning(f"Could not load positions: {e}")

    st.markdown("---")

    # ── Quick Actions ─────────────────────────────────────────────────
    st.subheader("⚡ Quick Actions")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📊 Option Chain", use_container_width=True):
        State.go("Option Chain"); st.rerun()
    if c2.button("💰 Sell Options", use_container_width=True):
        State.go("Sell Options"); st.rerun()
    if c3.button("🔄 Square Off", use_container_width=True):
        State.go("Square Off"); st.rerun()
    if c4.button("📋 Orders & Trades", use_container_width=True):
        State.go("Orders & Trades"); st.rerun()


def _welcome():
    c1, c2, c3 = st.columns(3)
    c1.markdown("### 📊 Data\n- Option chain\n- Live quotes\n- OI analysis")
    c2.markdown("### 💰 Trade\n- Sell options\n- Square off\n- Order tracking")
    c3.markdown("### 🛡️ Risk\n- Margin calc\n- P&L tracking\n- Debug mode")

    st.markdown("---")
    st.subheader("📈 Supported Instruments")
    rows = [{
        "Display Name": name,
        "API Code": cfg["stock_code"],
        "Exchange": cfg["exchange"],
        "Lot Size": cfg["lot_size"],
        "Strike Gap": cfg["strike_gap"],
        "Expiry Day": cfg["expiry_day"],
    } for name, cfg in Config.INSTRUMENTS.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.info("👈 **Login to start trading**")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: OPTION CHAIN
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_option_chain():
    st.markdown('<div class="page-header">📊 Option Chain</div>',
                unsafe_allow_html=True)
    cl = State.client()
    if not cl:
        st.warning("Connect first"); return

    # ── Controls ──────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="oc_inst")
    cfg = Config.INSTRUMENTS[instrument]
    expiries = Config.get_next_expiries(instrument, 5)
    with c2:
        expiry = st.selectbox("Expiry", expiries,
                              format_func=Utils.format_expiry_date, key="oc_exp")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", key="oc_ref", use_container_width=True)

    # ── Filters ───────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        filt = st.radio("Show", ["All", "Calls Only", "Puts Only"],
                        horizontal=True, key="oc_filt")
    with c2:
        num_strikes = st.slider("Strikes around ATM", 5, 30, 15, key="oc_ns")

    # ── Fetch / Cache ─────────────────────────────────────────────────
    cache_key = f"oc_{cfg['stock_code']}_{expiry}"
    cached = None if refresh else State.get_oc_cache(cache_key)

    if cached is not None:
        df = cached
        st.caption("📦 Cached (refreshes every 30s)")
    else:
        with st.spinner("Loading option chain..."):
            raw = cl.get_option_chain(cfg["stock_code"], cfg["exchange"], expiry)
        resp = APIResp(raw)
        if not resp.ok:
            st.error(f"Failed: {resp.msg}"); return
        df = OptionChainAnalyzer.process_option_chain(raw.get("data", {}))
        if df.empty:
            st.warning("No data available"); return
        State.cache_oc(cache_key, df)

    # ── Metrics ───────────────────────────────────────────────────────
    st.subheader(f"{instrument} ({cfg['stock_code']}) — {Utils.format_expiry_date(expiry)}")
    pcr = OptionChainAnalyzer.calculate_pcr(df)
    max_pain = OptionChainAnalyzer.get_max_pain(df, cfg["strike_gap"])
    call_oi = df[df["right"] == "Call"]["open_interest"].sum() if "right" in df.columns else 0
    put_oi = df[df["right"] == "Put"]["open_interest"].sum() if "right" in df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PCR", f"{pcr:.2f}", delta="Bullish" if pcr > 1 else "Bearish")
    c2.metric("Max Pain", f"{max_pain:,}")
    c3.metric("Call OI", f"{call_oi:,.0f}")
    c4.metric("Put OI", f"{put_oi:,.0f}")

    st.markdown("---")

    # ── Filter data ───────────────────────────────────────────────────
    show = df.copy()
    if "right" in show.columns:
        if filt == "Calls Only":
            show = show[show["right"] == "Call"]
        elif filt == "Puts Only":
            show = show[show["right"] == "Put"]

    if "strike_price" in show.columns and not show.empty:
        strikes = sorted(show["strike_price"].unique())
        mid = len(strikes) // 2
        lo = max(0, mid - num_strikes)
        hi = min(len(strikes), mid + num_strikes + 1)
        show = show[show["strike_price"].isin(strikes[lo:hi])]

    # ── Display ───────────────────────────────────────────────────────
    cols = ["strike_price", "right", "ltp", "open_interest", "volume",
            "best_bid_price", "best_offer_price", "ltp_percent_change"]
    avail = [c for c in cols if c in show.columns]
    names = {"strike_price": "Strike", "right": "Type", "ltp": "LTP",
             "open_interest": "OI", "volume": "Vol", "best_bid_price": "Bid",
             "best_offer_price": "Ask", "ltp_percent_change": "Chg%"}
    if avail:
        st.dataframe(show[avail].rename(columns=names),
                     use_container_width=True, height=500, hide_index=True)

    # ── OI Chart ──────────────────────────────────────────────────────
    if "right" in show.columns and "strike_price" in show.columns and "open_interest" in show.columns:
        st.markdown("---")
        st.subheader("📊 OI Distribution")
        calls = show[show["right"] == "Call"][["strike_price", "open_interest"]].rename(
            columns={"open_interest": "Call OI"})
        puts = show[show["right"] == "Put"][["strike_price", "open_interest"]].rename(
            columns={"open_interest": "Put OI"})
        merged = pd.merge(calls, puts, on="strike_price", how="outer").fillna(0).sort_values("strike_price")
        st.bar_chart(merged.set_index("strike_price"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SELL OPTIONS
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_sell_options():
    st.markdown('<div class="page-header">💰 Sell Options</div>',
                unsafe_allow_html=True)
    cl = State.client()
    if not cl:
        st.warning("Connect first"); return

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### 📋 Contract")
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="sl_inst")
        cfg = Config.INSTRUMENTS[instrument]
        expiry = st.selectbox("Expiry", Config.get_next_expiries(instrument, 5),
                              format_func=Utils.format_expiry_date, key="sl_exp")
        opt = st.radio("Option", ["CE (Call)", "PE (Put)"], horizontal=True, key="sl_opt")
        opt_code = "CE" if "CE" in opt else "PE"
        strike = st.number_input("Strike", min_value=0, step=cfg["strike_gap"], key="sl_str",
                                 help=f"Multiple of {cfg['strike_gap']}")
        if strike > 0 and strike % cfg["strike_gap"] != 0:
            st.warning(f"⚠️ Must be multiple of {cfg['strike_gap']}")

    with c2:
        st.markdown("#### 📝 Order")
        lots = st.number_input("Lots", 1, 100, 1, key="sl_lots")
        qty = lots * cfg["lot_size"]
        st.info(f"**Qty:** {qty} ({lots} × {cfg['lot_size']})")
        otype = st.radio("Order Type", ["Market", "Limit"], horizontal=True, key="sl_ot")
        price = 0.0
        if otype == "Limit":
            price = st.number_input("Price ₹", min_value=0.0, step=0.05, key="sl_pr")

    st.markdown("---")

    # ── Quote & Margin ────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📊 Get Quote", use_container_width=True, disabled=strike <= 0):
            with st.spinner("Fetching..."):
                q = APIResp(cl.get_quotes(cfg["stock_code"], cfg["exchange"], expiry, strike, opt_code))
                if q.ok:
                    d = q.items[0] if q.items else q.data
                    st.success(f"**LTP:** ₹{d.get('ltp','N/A')} · "
                               f"**Bid:** ₹{d.get('best_bid_price','N/A')} · "
                               f"**Ask:** ₹{d.get('best_offer_price','N/A')}")
                else:
                    st.error(q.msg)
    with c2:
        if st.button("💰 Margin", use_container_width=True, disabled=strike <= 0):
            with st.spinner("Calculating..."):
                m = APIResp(cl.get_margin_required(
                    cfg["stock_code"], cfg["exchange"], expiry, strike, opt_code, "sell", qty))
                if m.ok:
                    st.info(f"**Margin Required:** ₹{m.get('required_margin','N/A')}")
                else:
                    st.warning("Could not calculate margin")

    st.markdown("---")

    # ── Risk warning & order ──────────────────────────────────────────
    st.markdown("""<div class="danger-box">
    <b>⚠️ RISK WARNING:</b> Option selling has <b>UNLIMITED RISK</b>.
    </div>""", unsafe_allow_html=True)

    confirm = st.checkbox("I understand the risks", key="sl_conf")
    valid = confirm and strike > 0 and strike % cfg["strike_gap"] == 0 and (otype == "Market" or price > 0)

    if st.button(f"🔴 SELL {opt_code}", type="primary",
                 use_container_width=True, disabled=not valid):
        with st.spinner("Placing order..."):
            fn = cl.sell_call if opt_code == "CE" else cl.sell_put
            r = APIResp(fn(cfg["stock_code"], cfg["exchange"], expiry,
                           strike, qty, otype.lower(), price))
            if r.ok:
                st.markdown(f"""<div class="success-box">
                ✅ <b>Order Placed!</b><br>
                ID: {r.get('order_id','N/A')}<br>
                {instrument} ({cfg['stock_code']}) {strike} {opt_code} × {qty}
                </div>""", unsafe_allow_html=True)
                st.balloons()
            else:
                st.error(f"❌ {r.msg}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SQUARE OFF
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_square_off():
    st.markdown('<div class="page-header">🔄 Square Off</div>',
                unsafe_allow_html=True)
    cl = State.client()
    if not cl:
        st.warning("Connect first"); return

    debug = st.session_state.get("debug_mode", False)

    with st.spinner("Loading positions..."):
        resp = APIResp(cl.get_portfolio_positions())

    if not resp.ok:
        st.error(f"Failed: {resp.msg}"); return

    # Build list of open option positions
    opts = []
    for p in resp.items:
        if str(p.get("product_type", "")).lower() != "options":
            continue
        qty = safe_int(p.get("quantity", 0))
        if qty == 0:
            continue
        pt = detect_position_type(p)
        avg = safe_float(p.get("average_price", 0))
        ltp = safe_float(p.get("ltp", avg))
        p["_type"] = pt
        p["_qty"] = abs(qty)
        p["_action"] = close_action(pt)
        p["_pnl"] = calc_pnl(pt, avg, ltp, abs(qty))
        opts.append(p)

    if not opts:
        st.info("📭 No open option positions"); return

    st.success(f"**{len(opts)}** open position(s)")

    # ── Table ─────────────────────────────────────────────────────────
    rows = [{
        "Instrument": Config.get_instrument_display(p.get("stock_code", "")),
        "API Code": p.get("stock_code", ""),
        "Strike": p.get("strike_price", ""),
        "Option": p.get("right", ""),
        "Expiry": p.get("expiry_date", ""),
        "Qty": p["_qty"],
        "Position": p["_type"].upper(),
        "Avg": f"₹{safe_float(p.get('average_price',0)):.2f}",
        "LTP": f"₹{safe_float(p.get('ltp',0)):.2f}",
        "P&L": f"₹{p['_pnl']:+,.2f}",
        "To Close": p["_action"].upper(),
    } for p in opts]

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Debug ─────────────────────────────────────────────────────────
    if debug:
        with st.expander("🔧 Raw Position Data"):
            for i, p in enumerate(opts):
                st.write(f"**Position {i+1}:**")
                st.json({k: v for k, v in p.items() if not k.startswith("_")})

    st.markdown("---")

    # ── Individual Square Off ─────────────────────────────────────────
    st.subheader("Square Off Individual")
    labels = [
        f"{Config.get_instrument_display(p.get('stock_code',''))} "
        f"{p.get('strike_price')} {p.get('right')} | "
        f"{p['_type'].upper()} | Qty:{p['_qty']} | "
        f"Action:{p['_action'].upper()}"
        for p in opts
    ]
    idx = st.selectbox("Select Position", range(len(labels)),
                       format_func=lambda x: labels[x])
    sel = opts[idx]

    # Clear info about what happens
    if sel["_type"] == "short":
        st.markdown("""<div class="info-box">
        📌 This is a <b>SHORT</b> position. We will <b>BUY</b> to close it.
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""<div class="info-box">
        📌 This is a <b>LONG</b> position. We will <b>SELL</b> to close it.
        </div>""", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        sq_otype = st.radio("Order", ["Market", "Limit"], horizontal=True, key="sq_ot")
    with c2:
        sq_price = 0.0
        if sq_otype == "Limit":
            sq_price = st.number_input("Price", min_value=0.0, step=0.05, key="sq_pr")

    sq_qty = st.slider("Quantity", 1, sel["_qty"], sel["_qty"], key="sq_qty")

    btn = f"🔄 {sel['_action'].upper()} {sq_qty} to Close"
    if st.button(btn, type="primary", use_container_width=True):
        with st.spinner(f"Executing {sel['_action'].upper()} order..."):
            r = APIResp(cl.square_off_position(
                stock_code=sel.get("stock_code"),
                exchange=sel.get("exchange_code"),
                expiry_date=sel.get("expiry_date"),
                strike_price=safe_int(sel.get("strike_price", 0)),
                option_type=str(sel.get("right", "")).upper(),
                quantity=sq_qty,
                current_position=sel["_type"],
                order_type=sq_otype.lower(),
                price=sq_price,
            ))
            if r.ok:
                st.success(f"✅ {sel['_action'].upper()} order placed!")
                time.sleep(1); st.rerun()
            else:
                st.error(f"❌ {r.msg}")

    st.markdown("---")

    # ── Square Off All ────────────────────────────────────────────────
    st.subheader("⚡ Square Off ALL")
    st.markdown("""<div class="danger-box">
    ⚠️ Closes <b>ALL</b> open option positions at market price.
    </div>""", unsafe_allow_html=True)
    confirm = st.checkbox("I confirm", key="sq_all")
    if st.button("🔴 SQUARE OFF ALL", disabled=not confirm, use_container_width=True):
        with st.spinner("Closing all..."):
            results = cl.square_off_all()
            ok = sum(1 for r in results if r.get("success"))
            fail = len(results) - ok
            if ok: st.success(f"✅ Closed {ok}")
            if fail: st.warning(f"⚠️ Failed {fail}")
            time.sleep(1); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ORDERS & TRADES
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_orders_trades():
    st.markdown('<div class="page-header">📋 Orders & Trades</div>',
                unsafe_allow_html=True)
    cl = State.client()
    if not cl:
        st.warning("Connect first"); return

    # ── Two sub-tabs ──────────────────────────────────────────────────
    tab_orders, tab_trades = st.tabs(["📋 Orders", "📊 Trades"])

    # ══════════════════════════════════════════════════════════════════
    # TAB: ORDERS
    # ══════════════════════════════════════════════════════════════════
    with tab_orders:
        st.subheader("Order Book")

        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c1:
            exch = st.selectbox("Exchange", ["All", "NFO", "BFO"], key="ord_exch")
        with c2:
            from_d = st.date_input("From", datetime.now().date() - timedelta(days=7), key="ord_from")
        with c3:
            to_d = st.date_input("To", datetime.now().date(), key="ord_to")
        with c4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="ord_ref", use_container_width=True):
                st.rerun()

        # Fetch orders
        with st.spinner("Loading orders..."):
            resp = APIResp(cl.get_order_list(
                "" if exch == "All" else exch,
                from_d.strftime("%Y-%m-%d"),
                to_d.strftime("%Y-%m-%d"),
            ))

        if not resp.ok:
            st.error(f"Failed: {resp.msg}")
        else:
            olist = resp.items
            if not olist:
                st.info("📭 No orders found")
            else:
                # Summary
                total = len(olist)
                executed = sum(1 for o in olist if str(o.get("order_status", "")).lower() == "executed")
                pending = sum(1 for o in olist if str(o.get("order_status", "")).lower() in ("pending", "open"))
                rejected = sum(1 for o in olist if str(o.get("order_status", "")).lower() == "rejected")
                cancelled = sum(1 for o in olist if str(o.get("order_status", "")).lower() == "cancelled")

                mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                mc1.metric("Total", total)
                mc2.metric("Executed", executed)
                mc3.metric("Pending", pending)
                mc4.metric("Rejected", rejected)
                mc5.metric("Cancelled", cancelled)

                st.markdown("---")

                # Table
                df = pd.DataFrame(olist)
                show_cols = ["order_id", "stock_code", "action", "quantity", "price",
                             "order_type", "order_status", "strike_price", "right",
                             "expiry_date", "order_datetime"]
                avail = [c for c in show_cols if c in df.columns]
                rename = {
                    "order_id": "ID", "stock_code": "Code", "action": "Action",
                    "quantity": "Qty", "price": "Price", "order_type": "Type",
                    "order_status": "Status", "strike_price": "Strike",
                    "right": "Option", "expiry_date": "Expiry",
                    "order_datetime": "Time",
                }
                if avail:
                    st.dataframe(df[avail].rename(columns=rename),
                                 use_container_width=True, height=400, hide_index=True)
                else:
                    st.dataframe(df, use_container_width=True, height=400)

                # ── Manage Pending ────────────────────────────────────
                pending_orders = [
                    o for o in olist
                    if str(o.get("order_status", "")).lower() in ("pending", "open")
                ]

                if pending_orders:
                    st.markdown("---")
                    st.subheader("⚙️ Manage Pending Orders")

                    plabels = [
                        f"#{o.get('order_id','?')} | "
                        f"{o.get('stock_code','')} {o.get('action','')} "
                        f"{o.get('quantity','')} @ ₹{o.get('price','')}"
                        for o in pending_orders
                    ]
                    pidx = st.selectbox("Select Order", range(len(plabels)),
                                        format_func=lambda x: plabels[x], key="ord_sel")
                    psel = pending_orders[pidx]

                    # Show order details
                    with st.expander("📄 Order Details", expanded=True):
                        dc1, dc2, dc3 = st.columns(3)
                        dc1.write(f"**ID:** {psel.get('order_id')}")
                        dc1.write(f"**Code:** {psel.get('stock_code')}")
                        dc2.write(f"**Action:** {psel.get('action')}")
                        dc2.write(f"**Strike:** {psel.get('strike_price')}")
                        dc3.write(f"**Qty:** {psel.get('quantity')}")
                        dc3.write(f"**Price:** ₹{psel.get('price')}")

                    ac1, ac2 = st.columns(2)

                    with ac1:
                        if st.button("❌ Cancel Order", use_container_width=True, key="ord_cancel"):
                            with st.spinner("Cancelling..."):
                                cr = APIResp(cl.cancel_order(
                                    psel.get("order_id"),
                                    psel.get("exchange_code"),
                                ))
                                if cr.ok:
                                    st.success("✅ Cancelled!")
                                    time.sleep(1); st.rerun()
                                else:
                                    st.error(f"❌ {cr.msg}")

                    with ac2:
                        with st.expander("✏️ Modify Order"):
                            new_price = st.number_input(
                                "New Price", min_value=0.0,
                                value=safe_float(psel.get("price", 0)),
                                step=0.05, key="ord_mod_price",
                            )
                            new_qty = st.number_input(
                                "New Qty", min_value=1,
                                value=max(1, safe_int(psel.get("quantity", 1))),
                                key="ord_mod_qty",
                            )
                            if st.button("💾 Save Changes", use_container_width=True, key="ord_mod_save"):
                                with st.spinner("Modifying..."):
                                    mr = APIResp(cl.modify_order(
                                        psel.get("order_id"),
                                        psel.get("exchange_code"),
                                        new_qty, new_price,
                                    ))
                                    if mr.ok:
                                        st.success("✅ Modified!")
                                        time.sleep(1); st.rerun()
                                    else:
                                        st.error(f"❌ {mr.msg}")

    # ══════════════════════════════════════════════════════════════════
    # TAB: TRADES
    # ══════════════════════════════════════════════════════════════════
    with tab_trades:
        st.subheader("Trade Book")

        tc1, tc2, tc3, tc4 = st.columns([1, 1, 1, 1])
        with tc1:
            t_exch = st.selectbox("Exchange", ["All", "NFO", "BFO"], key="trd_exch")
        with tc2:
            t_from = st.date_input("From", datetime.now().date() - timedelta(days=7), key="trd_from")
        with tc3:
            t_to = st.date_input("To", datetime.now().date(), key="trd_to")
        with tc4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", key="trd_ref", use_container_width=True):
                st.rerun()

        with st.spinner("Loading trades..."):
            tresp = APIResp(cl.get_trade_list(
                "" if t_exch == "All" else t_exch,
                t_from.strftime("%Y-%m-%d"),
                t_to.strftime("%Y-%m-%d"),
            ))

        if not tresp.ok:
            st.error(f"Failed: {tresp.msg}")
        else:
            tlist = tresp.items
            if not tlist:
                st.info("📭 No trades found")
            else:
                # Summary
                buy_count = sum(1 for t in tlist if str(t.get("action", "")).lower() == "buy")
                sell_count = sum(1 for t in tlist if str(t.get("action", "")).lower() == "sell")

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Total Trades", len(tlist))
                mc2.metric("Buys", buy_count)
                mc3.metric("Sells", sell_count)

                st.markdown("---")

                # Table
                tdf = pd.DataFrame(tlist)
                tcols = ["trade_id", "order_id", "stock_code", "action",
                         "quantity", "trade_price", "strike_price", "right",
                         "expiry_date", "trade_datetime", "exchange_code"]
                tavail = [c for c in tcols if c in tdf.columns]
                trename = {
                    "trade_id": "Trade ID", "order_id": "Order ID",
                    "stock_code": "Code", "action": "Action",
                    "quantity": "Qty", "trade_price": "Price",
                    "strike_price": "Strike", "right": "Option",
                    "expiry_date": "Expiry", "trade_datetime": "Time",
                    "exchange_code": "Exchange",
                }
                if tavail:
                    st.dataframe(tdf[tavail].rename(columns=trename),
                                 use_container_width=True, height=400, hide_index=True)
                else:
                    st.dataframe(tdf, use_container_width=True, height=400)

                # Trade details
                if st.session_state.get("debug_mode"):
                    with st.expander("🔧 Raw Trade Data"):
                        st.json(tlist[:5])  # Show first 5


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: POSITIONS
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_positions():
    st.markdown('<div class="page-header">📍 Positions</div>',
                unsafe_allow_html=True)
    cl = State.client()
    if not cl:
        st.warning("Connect first"); return

    debug = st.session_state.get("debug_mode", False)

    if st.button("🔄 Refresh", key="pos_ref", use_container_width=True):
        st.rerun()

    with st.spinner("Loading..."):
        resp = APIResp(cl.get_portfolio_positions())

    if not resp.ok:
        st.error(f"Failed: {resp.msg}"); return

    plist = resp.items
    if not plist:
        st.info("📭 No positions"); return

    # ── Process ───────────────────────────────────────────────────────
    enhanced = []
    total_pnl = 0.0

    for p in plist:
        qty = safe_int(p.get("quantity", 0))
        if qty == 0:
            continue
        pt = detect_position_type(p)
        aq = abs(qty)
        avg = safe_float(p.get("average_price", 0))
        ltp = safe_float(p.get("ltp", avg))
        pnl = calc_pnl(pt, avg, ltp, aq)
        total_pnl += pnl

        enhanced.append({
            "stock_code": p.get("stock_code", ""),
            "display": Config.get_instrument_display(p.get("stock_code", "")),
            "exchange": p.get("exchange_code", ""),
            "expiry": p.get("expiry_date", ""),
            "strike": p.get("strike_price", ""),
            "right": p.get("right", ""),
            "qty": aq, "type": pt, "avg": avg, "ltp": ltp, "pnl": pnl,
            "_raw": p,
        })

    if not enhanced:
        st.info("📭 No active positions"); return

    # ── Summary ───────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(enhanced))
    c2.metric("Long", sum(1 for e in enhanced if e["type"] == "long"))
    c3.metric("Short", sum(1 for e in enhanced if e["type"] == "short"))
    c4.metric("P&L", f"₹{total_pnl:+,.2f}",
              delta_color="normal" if total_pnl >= 0 else "inverse")

    st.markdown("---")

    # ── Table ─────────────────────────────────────────────────────────
    rows = [{
        "Instrument": e["display"],
        "Code": e["stock_code"],
        "Strike": e["strike"],
        "Option": e["right"],
        "Expiry": e["expiry"],
        "Qty": e["qty"],
        "Position": e["type"].upper(),
        "Avg": f"₹{e['avg']:.2f}",
        "LTP": f"₹{e['ltp']:.2f}",
        "P&L": f"₹{e['pnl']:+,.2f}",
        "To Close": close_action(e["type"]).upper(),
    } for e in enhanced]

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Debug ─────────────────────────────────────────────────────────
    if debug:
        st.markdown("---")
        st.subheader("🔧 Debug: Raw Data")
        for i, e in enumerate(enhanced):
            with st.expander(f"Pos {i+1}: {e['stock_code']} {e['strike']}"):
                st.write(f"**Detected:** {e['type'].upper()}")
                if e["type"] == "short":
                    st.code(f"P&L = (Avg−LTP)×Qty = ({e['avg']}−{e['ltp']})×{e['qty']} = {e['pnl']:.2f}")
                else:
                    st.code(f"P&L = (LTP−Avg)×Qty = ({e['ltp']}−{e['avg']})×{e['qty']} = {e['pnl']:.2f}")
                st.json(e["_raw"])

    st.markdown("---")

    # ── Details ───────────────────────────────────────────────────────
    st.subheader("📊 Position Details")

    for e in enhanced:
        emoji = "📈" if e["pnl"] >= 0 else "📉"
        badge = "🟢 LONG" if e["type"] == "long" else "🔴 SHORT"
        act = close_action(e["type"])

        with st.expander(
            f"{emoji} {e['display']} {e['strike']} {e['right']} "
            f"| {badge} | P&L: ₹{e['pnl']:+,.2f}"
        ):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Contract**")
                st.write(f"API Code: {e['stock_code']}")
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
                color = "profit" if e["pnl"] >= 0 else "loss"
                st.markdown(f"<span class='{color}'>₹{e['pnl']:+,.2f}</span>",
                            unsafe_allow_html=True)
                if e["avg"] > 0:
                    pct = (e["pnl"] / (e["avg"] * e["qty"])) * 100
                    st.write(f"Return: {pct:+.2f}%")
                st.write(f"To close: **{act.upper()}**")

            if st.button(f"🔄 Go to Square Off",
                         key=f"sq_{e['stock_code']}_{e['strike']}_{e['right']}",
                         use_container_width=True):
                State.go("Square Off"); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════

PAGES = {
    "Dashboard":       page_dashboard,
    "Option Chain":    page_option_chain,
    "Sell Options":    page_sell_options,
    "Square Off":      page_square_off,
    "Orders & Trades": page_orders_trades,
    "Positions":       page_positions,
}

AUTH_REQUIRED = {"Option Chain", "Sell Options", "Square Off",
                 "Orders & Trades", "Positions"}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    State.init()
    render_sidebar()

    st.markdown('<h1 class="main-header">📈 Breeze Options Trader</h1>',
                unsafe_allow_html=True)
    st.markdown("---")

    page = State.page()
    fn = PAGES.get(page, page_dashboard)

    if page in AUTH_REQUIRED and not State.authed():
        st.warning("🔒 Please login to access this page")
        st.info("👈 Enter credentials in the sidebar")
        return

    fn()


if __name__ == "__main__":
    main()
