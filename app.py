"""
Breeze Options Trader — Main Application.
═════════════════════════════════════════
v3.3 — Smart credential management:
  • API Key & Secret from Streamlit Secrets (set once)
  • Only Session Token entered daily via UI
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from functools import wraps
import time
import logging

from app_config import Config
from session_manager import SessionManager, CredentialManager, NotificationManager
from breeze_client import BreezeClientWrapper
from utils import Utils, OptionChainAnalyzer, PositionUtils

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
.cred-ok { color:#28a745; }
.cred-missing { color:#dc3545; }
.profit  { color:#28a745!important; font-weight:bold; }
.loss    { color:#dc3545!important; font-weight:bold; }
.warning-box { background:#fff3cd; border-left:4px solid #ffc107;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0; }
.info-box { background:#e7f3ff; border-left:4px solid #2196F3;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0; }
.success-box { background:#d4edda; border-left:4px solid #28a745;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0; }
.danger-box { background:#f8d7da; border-left:4px solid #dc3545;
    padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0; }
.stButton>button { width:100%; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def safe_int(v):
    try: return int(float(str(v).strip())) if v else 0
    except: return 0

def safe_float(v):
    try: return float(str(v).strip()) if v else 0.0
    except: return 0.0


class APIResp:
    """Normalise Breeze responses (Success can be dict or list)."""
    def __init__(self, raw: Dict):
        self.raw = raw
        self.ok = raw.get("success", False)
        self.msg = raw.get("message", "Unknown error")
        d = raw.get("data", {})
        s = d.get("Success") if isinstance(d, dict) else None
        if isinstance(s, dict):
            self._single = s
        elif isinstance(s, list) and s and isinstance(s[0], dict):
            self._single = s[0]
        else:
            self._single = {}

    @property
    def data(self): return self._single

    @property
    def items(self):
        if not self.ok: return []
        d = self.raw.get("data", {})
        s = d.get("Success") if isinstance(d, dict) else None
        if isinstance(s, list): return s
        if isinstance(s, dict): return [s]
        return []

    def get(self, k, default=None): return self._single.get(k, default)


def api_guard(fn):
    @wraps(fn)
    def w(*a, **kw):
        try: return fn(*a, **kw)
        except Exception as e:
            logger.error(f"{fn.__name__}: {e}")
            st.error(f"❌ {e}")
    return w


# ══════════════════════════════════════════════════════════════════════════════
# NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

ALL_PAGES = [
    "Dashboard", "Option Chain", "Sell Options",
    "Square Off", "Orders & Trades", "Positions",
]
PAGE_ICONS = {
    "Dashboard": "🏠", "Option Chain": "📊", "Sell Options": "💰",
    "Square Off": "🔄", "Orders & Trades": "📋", "Positions": "📍",
}
AUTH_REQUIRED = {"Option Chain", "Sell Options", "Square Off",
                 "Orders & Trades", "Positions"}


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    with st.sidebar:
        st.markdown("## 📈 Breeze Trader")
        st.markdown("---")

        # Navigation
        available = ALL_PAGES if SessionManager.is_authenticated() else ["Dashboard"]
        cur = SessionManager.get_page()
        if cur not in available:
            cur = "Dashboard"

        sel = st.radio(
            "Navigation", available,
            index=available.index(cur),
            format_func=lambda p: f"{PAGE_ICONS.get(p, '📄')} {p}",
            label_visibility="collapsed",
        )
        if sel != cur:
            SessionManager.set_page(sel)
            st.rerun()

        st.markdown("---")

        # Authentication
        if not SessionManager.is_authenticated():
            _render_smart_login()
        else:
            _render_account_panel()

        st.markdown("---")

        # Settings
        st.markdown("### ⚙️ Settings")
        st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()),
                     key="selected_instrument")
        st.session_state.debug_mode = st.checkbox(
            "🔧 Debug", value=st.session_state.get("debug_mode", False))

        st.markdown("---")
        st.caption("Breeze Options Trader v3.3")


def _render_smart_login():
    """
    Smart login flow:
    • If API Key & Secret are in Streamlit Secrets → only ask for Session Token
    • If not → ask for all three
    """
    has_secrets = CredentialManager.has_stored_credentials()

    if has_secrets:
        # ── FAST LOGIN: Only Session Token ────────────────────────────
        st.markdown("### 🔑 Daily Login")

        st.markdown("""
        <div class="success-box">
        ✅ API Key & Secret loaded from secrets.<br>
        Just enter today's <b>Session Token</b>.
        </div>
        """, unsafe_allow_html=True)

        with st.form("fast_login", clear_on_submit=False):
            token = st.text_input(
                "Session Token",
                type="password",
                placeholder="Paste today's session token",
                help="Get from ICICI Direct → API → Generate Session Token",
            )

            if st.form_submit_button("🔑 Connect", use_container_width=True):
                if not token:
                    st.warning("⚠️ Enter session token")
                    return

                api_key = CredentialManager.get_stored_api_key()
                api_secret = CredentialManager.get_stored_api_secret()

                with st.spinner("Connecting..."):
                    client = BreezeClientWrapper(api_key, api_secret)
                    result = client.connect(token)

                    if result["success"]:
                        CredentialManager.save_session_credentials(
                            api_key, api_secret, token)
                        SessionManager.set_authenticated(True, client)
                        NotificationManager.toast("Connected!", "✅")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"❌ {result['message']}")
                        logger.error(f"Login failed: {result['message']}")

        # Link to full login
        with st.expander("🔧 Use different credentials"):
            _render_full_login()

    else:
        # ── FULL LOGIN: All three credentials ─────────────────────────
        st.markdown("### 🔐 Login")

        st.markdown("""
        <div class="info-box">
        💡 <b>Tip:</b> Store API Key & Secret in
        <a href="https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management"
           target="_blank">Streamlit Secrets</a>
        so you only need to enter the Session Token daily.
        </div>
        """, unsafe_allow_html=True)

        _render_full_login()


def _render_full_login():
    """Full login form with all three fields."""
    with st.form("full_login", clear_on_submit=False):
        api_key, api_secret, _ = CredentialManager.get_all_credentials()

        nk = st.text_input("API Key", value=api_key, type="password")
        ns = st.text_input("API Secret", value=api_secret, type="password")
        nt = st.text_input("Session Token", type="password",
                           placeholder="Today's token from ICICI")

        st.caption("💡 Session token changes daily from ICICI Direct")

        if st.form_submit_button("🔑 Connect", use_container_width=True):
            if not all([nk, ns, nt]):
                st.warning("Fill all fields")
                return

            with st.spinner("Connecting..."):
                client = BreezeClientWrapper(nk, ns)
                result = client.connect(nt)

                if result["success"]:
                    CredentialManager.save_session_credentials(nk, ns, nt)
                    SessionManager.set_authenticated(True, client)
                    st.success("✅ Connected!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")


def _render_account_panel():
    """Account info, session health, disconnect."""
    cl = SessionManager.get_client()
    if not cl:
        return

    st.markdown('<span class="status-connected">✅ Connected</span>',
                unsafe_allow_html=True)

    # User info
    try:
        r = APIResp(cl.get_customer_details())
        name = r.get("name", "User")
        st.session_state.user_name = name
        st.markdown(f"**👤 {name}**")
    except Exception:
        st.markdown(f"**👤 {st.session_state.get('user_name', 'User')}**")

    # Session duration
    duration = SessionManager.get_login_duration()
    if duration:
        st.caption(f"⏱️ Session: {duration}")

    # Session health warning
    if SessionManager.is_session_token_stale():
        st.warning("⚠️ Session may be stale — consider reconnecting")

    # Market status
    st.markdown(f"**{Utils.get_market_status()}**")

    # Funds (cached)
    try:
        cached_funds = SessionManager.get_cached_funds()
        if cached_funds:
            avail = safe_float(cached_funds.get("available_margin", 0))
        else:
            r = APIResp(cl.get_funds())
            avail = safe_float(r.get("available_margin", 0))
            if r.ok:
                SessionManager.cache_funds(r.data)
        st.metric("Margin", Utils.format_currency(avail))
    except Exception:
        pass

    # Credential status
    with st.expander("🔑 Credential Status"):
        status = CredentialManager.get_credential_status()
        for label, key, val in [
            ("API Key (secrets)", "api_key_in_secrets", status["api_key_in_secrets"]),
            ("API Secret (secrets)", "api_secret_in_secrets", status["api_secret_in_secrets"]),
            ("Session Token", "session_token_available", status["session_token_available"]),
        ]:
            icon = "✅" if val else "❌"
            st.write(f"{icon} {label}")

    # Disconnect
    if st.button("🔓 Disconnect", use_container_width=True):
        SessionManager.set_authenticated(False)
        CredentialManager.clear_session_credentials()
        SessionManager.set_page("Dashboard")
        SessionManager.clear_cache()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.markdown('<div class="page-header">🏠 Dashboard</div>',
                unsafe_allow_html=True)

    # Show any pending notifications
    NotificationManager.show_pending_messages()

    if not SessionManager.is_authenticated():
        _welcome()
        return

    cl = SessionManager.get_client()

    # Session health check
    if SessionManager.is_session_token_stale():
        st.markdown("""<div class="warning-box">
        ⚠️ <b>Session may be stale.</b> ICICI tokens reset daily.
        Consider disconnecting and entering today's session token.
        </div>""", unsafe_allow_html=True)

    # Account
    st.subheader(f"📈 {Utils.get_market_status()}")
    try:
        cached = SessionManager.get_cached_funds()
        if cached:
            f_data = cached
        else:
            f = APIResp(cl.get_funds())
            f_data = f.data if f.ok else {}
            if f.ok:
                SessionManager.cache_funds(f_data)

        av = safe_float(f_data.get("available_margin", 0))
        us = safe_float(f_data.get("utilized_margin", 0))
        c1, c2, c3 = st.columns(3)
        c1.metric("Available", Utils.format_currency(av))
        c2.metric("Used", Utils.format_currency(us))
        c3.metric("Total", Utils.format_currency(av + us))
    except Exception:
        pass

    st.markdown("---")

    # Positions summary
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
                pt = PositionUtils.detect_type(p)
                q = abs(safe_int(p.get("quantity", 0)))
                avg = safe_float(p.get("average_price", 0))
                ltp = safe_float(p.get("ltp", avg))
                pnl = PositionUtils.calc_pnl(pt, avg, ltp, q)
                total_pnl += pnl
                rows.append({
                    "Instrument": Config.get_instrument_display(p.get("stock_code", "")),
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

    # Quick actions
    st.subheader("⚡ Quick Actions")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📊 Option Chain", use_container_width=True):
        SessionManager.set_page("Option Chain"); st.rerun()
    if c2.button("💰 Sell Options", use_container_width=True):
        SessionManager.set_page("Sell Options"); st.rerun()
    if c3.button("🔄 Square Off", use_container_width=True):
        SessionManager.set_page("Square Off"); st.rerun()
    if c4.button("📋 Orders & Trades", use_container_width=True):
        SessionManager.set_page("Orders & Trades"); st.rerun()

    # Session activity log
    history = SessionManager.get_order_history()
    if history:
        st.markdown("---")
        st.subheader("📝 Recent Activity (this session)")
        st.dataframe(pd.DataFrame(history[:10]), hide_index=True, use_container_width=True)


def _welcome():
    c1, c2, c3 = st.columns(3)
    c1.markdown("### 📊 Data\n- Option chain\n- Live quotes\n- OI analysis")
    c2.markdown("### 💰 Trade\n- Sell options\n- Square off\n- Order tracking")
    c3.markdown("### 🛡️ Risk\n- Margin calc\n- P&L tracking\n- Debug mode")

    st.markdown("---")

    # Credential setup guide
    if not CredentialManager.has_stored_credentials():
        st.markdown("""<div class="info-box">
        <b>🔧 First-time Setup:</b><br><br>
        Store your API Key & Secret in Streamlit Secrets so you only
        enter the Session Token daily:<br><br>
        <b>Streamlit Cloud:</b> App → Manage → Settings → Secrets<br>
        <b>Local:</b> Create <code>.streamlit/secrets.toml</code><br><br>
        <pre>
BREEZE_API_KEY = "your_key"
BREEZE_API_SECRET = "your_secret"
        </pre>
        </div>""", unsafe_allow_html=True)

    st.subheader("📈 Supported Instruments")
    rows = [{
        "Name": name, "API Code": cfg["stock_code"],
        "Exchange": cfg["exchange"], "Lot": cfg["lot_size"],
        "Gap": cfg["strike_gap"], "Expiry": cfg["expiry_day"],
    } for name, cfg in Config.INSTRUMENTS.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.info("👈 **Login to start trading**")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: OPTION CHAIN
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_option_chain():
    st.markdown('<div class="page-header">📊 Option Chain</div>', unsafe_allow_html=True)
    cl = SessionManager.get_client()
    if not cl: st.warning("Connect first"); return

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="oc_inst")
    cfg = Config.INSTRUMENTS[instrument]
    with c2:
        expiry = st.selectbox("Expiry", Config.get_next_expiries(instrument, 5),
                              format_func=Utils.format_expiry_date, key="oc_exp")
    with c3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄", key="oc_ref", use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        filt = st.radio("Show", ["All", "Calls", "Puts"], horizontal=True, key="oc_filt")
    with c2:
        nstrikes = st.slider("Strikes", 5, 30, 15, key="oc_ns")

    cache_key = f"oc_{cfg['stock_code']}_{expiry}"
    cached = None if refresh else SessionManager.get_cached_option_chain(cache_key)

    if cached is not None:
        df = cached
        st.caption("📦 Cached")
    else:
        with st.spinner("Loading..."):
            raw = cl.get_option_chain(cfg["stock_code"], cfg["exchange"], expiry)
        r = APIResp(raw)
        if not r.ok: st.error(r.msg); return
        df = OptionChainAnalyzer.process_option_chain(raw.get("data", {}))
        if df.empty: st.warning("No data"); return
        SessionManager.cache_option_chain(cache_key, df)

    st.subheader(f"{instrument} ({cfg['stock_code']}) — {Utils.format_expiry_date(expiry)}")

    pcr = OptionChainAnalyzer.calculate_pcr(df)
    mp = OptionChainAnalyzer.get_max_pain(df, cfg["strike_gap"])
    call_oi = df[df["right"]=="Call"]["open_interest"].sum() if "right" in df.columns else 0
    put_oi = df[df["right"]=="Put"]["open_interest"].sum() if "right" in df.columns else 0

    mc = st.columns(4)
    mc[0].metric("PCR", f"{pcr:.2f}", delta="Bullish" if pcr > 1 else "Bearish")
    mc[1].metric("Max Pain", f"{mp:,}")
    mc[2].metric("Call OI", f"{call_oi:,.0f}")
    mc[3].metric("Put OI", f"{put_oi:,.0f}")

    show = df.copy()
    if "right" in show.columns:
        if filt == "Calls": show = show[show["right"]=="Call"]
        elif filt == "Puts": show = show[show["right"]=="Put"]

    if "strike_price" in show.columns and not show.empty:
        strikes = sorted(show["strike_price"].unique())
        mid = len(strikes)//2
        show = show[show["strike_price"].isin(strikes[max(0,mid-nstrikes):mid+nstrikes+1])]

    cols = ["strike_price","right","ltp","open_interest","volume","best_bid_price","best_offer_price"]
    avail = [c for c in cols if c in show.columns]
    names = {"strike_price":"Strike","right":"Type","ltp":"LTP","open_interest":"OI",
             "volume":"Vol","best_bid_price":"Bid","best_offer_price":"Ask"}
    st.dataframe(show[avail].rename(columns=names) if avail else show,
                 use_container_width=True, height=500, hide_index=True)

    if all(c in show.columns for c in ("right","strike_price","open_interest")):
        st.markdown("---")
        st.subheader("📊 OI Distribution")
        calls = show[show["right"]=="Call"][["strike_price","open_interest"]].rename(columns={"open_interest":"Call OI"})
        puts = show[show["right"]=="Put"][["strike_price","open_interest"]].rename(columns={"open_interest":"Put OI"})
        merged = pd.merge(calls, puts, on="strike_price", how="outer").fillna(0).sort_values("strike_price")
        st.bar_chart(merged.set_index("strike_price"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SELL OPTIONS
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_sell_options():
    st.markdown('<div class="page-header">💰 Sell Options</div>', unsafe_allow_html=True)
    cl = SessionManager.get_client()
    if not cl: st.warning("Connect first"); return

    c1, c2 = st.columns(2)
    with c1:
        inst = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="sl_i")
        cfg = Config.INSTRUMENTS[inst]
        exp = st.selectbox("Expiry", Config.get_next_expiries(inst,5),
                           format_func=Utils.format_expiry_date, key="sl_e")
        opt = st.radio("Option", ["CE (Call)","PE (Put)"], horizontal=True, key="sl_o")
        oc = "CE" if "CE" in opt else "PE"
        strike = st.number_input("Strike", min_value=0, step=cfg["strike_gap"], key="sl_s")
    with c2:
        lots = st.number_input("Lots", 1, 100, 1, key="sl_l")
        qty = lots * cfg["lot_size"]
        st.info(f"**Qty:** {qty} ({lots}×{cfg['lot_size']})")
        ot = st.radio("Order", ["Market","Limit"], horizontal=True, key="sl_ot")
        price = st.number_input("Price", min_value=0.0, step=0.05, key="sl_p") if ot=="Limit" else 0.0

    st.markdown("---")
    c1,c2 = st.columns(2)
    with c1:
        if st.button("📊 Quote", use_container_width=True, disabled=strike<=0):
            with st.spinner("..."):
                q = APIResp(cl.get_quotes(cfg["stock_code"],cfg["exchange"],exp,strike,oc))
                if q.ok:
                    d = q.items[0] if q.items else q.data
                    st.success(f"LTP: ₹{d.get('ltp','?')} | Bid: ₹{d.get('best_bid_price','?')} | Ask: ₹{d.get('best_offer_price','?')}")
                else: st.error(q.msg)
    with c2:
        if st.button("💰 Margin", use_container_width=True, disabled=strike<=0):
            with st.spinner("..."):
                m = APIResp(cl.get_margin_required(cfg["stock_code"],cfg["exchange"],exp,strike,oc,"sell",qty))
                st.info(f"Margin: ₹{m.get('required_margin','?')}") if m.ok else st.warning("N/A")

    st.markdown("""<div class="danger-box">⚠️ Option selling has <b>UNLIMITED RISK</b>.</div>""", unsafe_allow_html=True)
    conf = st.checkbox("I understand the risks", key="sl_c")
    ok = conf and strike>0 and strike%cfg["strike_gap"]==0 and (ot=="Market" or price>0)

    if st.button(f"🔴 SELL {oc}", type="primary", use_container_width=True, disabled=not ok):
        with st.spinner("Placing..."):
            fn = cl.sell_call if oc=="CE" else cl.sell_put
            r = APIResp(fn(cfg["stock_code"],cfg["exchange"],exp,strike,qty,ot.lower(),price))
            if r.ok:
                st.markdown(f"""<div class="success-box">✅ Order Placed! ID: {r.get('order_id','?')}</div>""", unsafe_allow_html=True)
                st.balloons()
                SessionManager.log_order({"action":"SELL","instrument":inst,"strike":strike,"type":oc,"qty":qty,"status":"placed"})
                NotificationManager.order_placed(inst, strike, oc, qty, "sell")
            else:
                st.error(f"❌ {r.msg}")
                NotificationManager.order_failed(r.msg)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SQUARE OFF
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_square_off():
    st.markdown('<div class="page-header">🔄 Square Off</div>', unsafe_allow_html=True)
    cl = SessionManager.get_client()
    if not cl: st.warning("Connect first"); return

    debug = st.session_state.get("debug_mode", False)

    with st.spinner("Loading..."):
        resp = APIResp(cl.get_portfolio_positions())
    if not resp.ok: st.error(resp.msg); return

    opts = []
    for p in resp.items:
        if str(p.get("product_type","")).lower() != "options": continue
        qty = safe_int(p.get("quantity",0))
        if qty == 0: continue
        pt = PositionUtils.detect_type(p)
        avg = safe_float(p.get("average_price",0))
        ltp = safe_float(p.get("ltp",avg))
        p["_type"]=pt; p["_qty"]=abs(qty)
        p["_action"]=PositionUtils.close_action(pt)
        p["_pnl"]=PositionUtils.calc_pnl(pt,avg,ltp,abs(qty))
        opts.append(p)

    if not opts: st.info("📭 No open option positions"); return
    st.success(f"**{len(opts)}** position(s)")

    rows = [{
        "Instrument": Config.get_instrument_display(p.get("stock_code","")),
        "Strike": p.get("strike_price",""), "Option": p.get("right",""),
        "Qty": p["_qty"], "Position": p["_type"].upper(),
        "P&L": f"₹{p['_pnl']:+,.2f}", "To Close": p["_action"].upper(),
    } for p in opts]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if debug:
        with st.expander("🔧 Raw"):
            for p in opts: st.json({k:v for k,v in p.items() if not k.startswith("_")})

    st.markdown("---")
    st.subheader("Square Off Individual")
    labels = [f"{Config.get_instrument_display(p.get('stock_code',''))} {p.get('strike_price')} {p.get('right')} | {p['_type'].upper()} | Qty:{p['_qty']}" for p in opts]
    idx = st.selectbox("Position", range(len(labels)), format_func=lambda x: labels[x])
    sel = opts[idx]

    act = sel["_action"]
    st.markdown(f"""<div class="info-box">📌 <b>{sel['_type'].upper()}</b> position → will <b>{act.upper()}</b> to close.</div>""", unsafe_allow_html=True)

    c1,c2 = st.columns(2)
    with c1: sq_ot = st.radio("Order",["Market","Limit"],horizontal=True,key="sq_ot")
    with c2: sq_pr = st.number_input("Price",min_value=0.0,step=0.05,key="sq_pr") if sq_ot=="Limit" else 0.0
    sq_q = st.slider("Qty",1,sel["_qty"],sel["_qty"],key="sq_q")

    if st.button(f"🔄 {act.upper()} {sq_q} to Close", type="primary", use_container_width=True):
        with st.spinner(f"{act.upper()}ing..."):
            r = APIResp(cl.square_off_position(
                sel.get("stock_code"), sel.get("exchange_code"), sel.get("expiry_date"),
                safe_int(sel.get("strike_price",0)), str(sel.get("right","")).upper(),
                sq_q, sel["_type"], sq_ot.lower(), sq_pr))
            if r.ok:
                st.success(f"✅ {act.upper()} order placed!")
                SessionManager.log_order({"action":act.upper(),"instrument":sel.get("stock_code"),"strike":sel.get("strike_price"),"qty":sq_q,"status":"squared off"})
                NotificationManager.position_closed(sel.get("stock_code",""), safe_int(sel.get("strike_price",0)))
                time.sleep(1); st.rerun()
            else: st.error(f"❌ {r.msg}")

    st.markdown("---")
    st.subheader("⚡ Square Off ALL")
    st.markdown("""<div class="danger-box">⚠️ Closes ALL at market.</div>""", unsafe_allow_html=True)
    if st.checkbox("Confirm",key="sq_all"):
        if st.button("🔴 SQUARE OFF ALL", use_container_width=True):
            with st.spinner("Closing..."):
                results = cl.square_off_all()
                ok = sum(1 for r in results if r.get("success"))
                if ok: st.success(f"✅ Closed {ok}")
                if len(results)-ok: st.warning(f"⚠️ Failed {len(results)-ok}")
                time.sleep(1); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ORDERS & TRADES
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_orders_trades():
    st.markdown('<div class="page-header">📋 Orders & Trades</div>', unsafe_allow_html=True)
    cl = SessionManager.get_client()
    if not cl: st.warning("Connect first"); return

    tab_o, tab_t, tab_h = st.tabs(["📋 Orders", "📊 Trades", "📝 Session Log"])

    with tab_o:
        st.subheader("Order Book")
        c1,c2,c3,c4 = st.columns([1,1,1,1])
        with c1: exch = st.selectbox("Exchange",["All","NFO","BFO"],key="o_e")
        with c2: fd = st.date_input("From",datetime.now().date()-timedelta(days=7),key="o_f")
        with c3: td = st.date_input("To",datetime.now().date(),key="o_t")
        with c4:
            st.markdown("<br>",unsafe_allow_html=True)
            if st.button("🔄",key="o_r",use_container_width=True): st.rerun()

        with st.spinner("Loading orders..."):
            resp = APIResp(cl.get_order_list("" if exch=="All" else exch, fd.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d")))

        if not resp.ok:
            st.error(resp.msg)
        else:
            olist = resp.items
            if not olist: st.info("📭 No orders")
            else:
                tot=len(olist)
                exe=sum(1 for o in olist if str(o.get("order_status","")).lower()=="executed")
                pen=sum(1 for o in olist if str(o.get("order_status","")).lower() in ("pending","open"))
                rej=sum(1 for o in olist if str(o.get("order_status","")).lower()=="rejected")
                mc=st.columns(4); mc[0].metric("Total",tot); mc[1].metric("Executed",exe); mc[2].metric("Pending",pen); mc[3].metric("Rejected",rej)
                st.dataframe(pd.DataFrame(olist), use_container_width=True, height=400, hide_index=True)

                pending=[o for o in olist if str(o.get("order_status","")).lower() in ("pending","open")]
                if pending:
                    st.markdown("---"); st.subheader("Manage Pending")
                    plbl=[f"#{o.get('order_id','?')} {o.get('stock_code','')} {o.get('action','')}" for o in pending]
                    pi=st.selectbox("Order",range(len(plbl)),format_func=lambda x:plbl[x],key="op_s")
                    ps=pending[pi]
                    c1,c2=st.columns(2)
                    with c1:
                        if st.button("❌ Cancel",use_container_width=True,key="op_c"):
                            with st.spinner("..."):
                                cr=APIResp(cl.cancel_order(ps.get("order_id"),ps.get("exchange_code")))
                                if cr.ok: st.success("✅ Cancelled"); time.sleep(1); st.rerun()
                                else: st.error(cr.msg)
                    with c2:
                        with st.expander("✏️ Modify"):
                            np=st.number_input("Price",min_value=0.0,value=safe_float(ps.get("price",0)),step=0.05,key="op_p")
                            nq=st.number_input("Qty",min_value=1,value=max(1,safe_int(ps.get("quantity",1))),key="op_q")
                            if st.button("💾 Save",key="op_sv"):
                                mr=APIResp(cl.modify_order(ps.get("order_id"),ps.get("exchange_code"),nq,np))
                                if mr.ok: st.success("✅"); time.sleep(1); st.rerun()
                                else: st.error(mr.msg)

    with tab_t:
        st.subheader("Trade Book")
        c1,c2,c3,c4 = st.columns([1,1,1,1])
        with c1: texch=st.selectbox("Exchange",["All","NFO","BFO"],key="t_e")
        with c2: tfd=st.date_input("From",datetime.now().date()-timedelta(days=7),key="t_f")
        with c3: ttd=st.date_input("To",datetime.now().date(),key="t_t")
        with c4:
            st.markdown("<br>",unsafe_allow_html=True)
            if st.button("🔄",key="t_r",use_container_width=True): st.rerun()

        with st.spinner("Loading trades..."):
            tresp=APIResp(cl.get_trade_list("" if texch=="All" else texch, tfd.strftime("%Y-%m-%d"), ttd.strftime("%Y-%m-%d")))

        if not tresp.ok: st.error(tresp.msg)
        else:
            tlist=tresp.items
            if not tlist: st.info("📭 No trades")
            else:
                bc=sum(1 for t in tlist if str(t.get("action","")).lower()=="buy")
                sc=sum(1 for t in tlist if str(t.get("action","")).lower()=="sell")
                mc=st.columns(3); mc[0].metric("Total",len(tlist)); mc[1].metric("Buys",bc); mc[2].metric("Sells",sc)
                st.dataframe(pd.DataFrame(tlist), use_container_width=True, height=400, hide_index=True)

    with tab_h:
        st.subheader("📝 Session Activity Log")
        hist = SessionManager.get_order_history()
        if hist:
            st.dataframe(pd.DataFrame(hist), hide_index=True, use_container_width=True)
        else:
            st.info("No activity this session")

        conn_log = SessionManager.get_connection_log()
        if conn_log:
            st.markdown("---")
            st.subheader("🔌 Connection Log")
            st.dataframe(pd.DataFrame(conn_log), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: POSITIONS
# ══════════════════════════════════════════════════════════════════════════════

@api_guard
def page_positions():
    st.markdown('<div class="page-header">📍 Positions</div>', unsafe_allow_html=True)
    cl = SessionManager.get_client()
    if not cl: st.warning("Connect first"); return

    debug = st.session_state.get("debug_mode",False)
    if st.button("🔄 Refresh",key="pos_r",use_container_width=True): st.rerun()

    with st.spinner("Loading..."):
        resp = APIResp(cl.get_portfolio_positions())
    if not resp.ok: st.error(resp.msg); return

    enhanced = []
    total_pnl = 0.0
    for p in resp.items:
        qty = safe_int(p.get("quantity",0))
        if qty==0: continue
        pt = PositionUtils.detect_type(p)
        aq = abs(qty)
        avg = safe_float(p.get("average_price",0))
        ltp = safe_float(p.get("ltp",avg))
        pnl = PositionUtils.calc_pnl(pt,avg,ltp,aq)
        total_pnl += pnl
        enhanced.append({
            "sc":p.get("stock_code",""), "disp":Config.get_instrument_display(p.get("stock_code","")),
            "exch":p.get("exchange_code",""), "expiry":p.get("expiry_date",""),
            "strike":p.get("strike_price",""), "right":p.get("right",""),
            "qty":aq, "type":pt, "avg":avg, "ltp":ltp, "pnl":pnl, "_raw":p,
        })

    if not enhanced: st.info("📭 No active positions"); return

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total",len(enhanced))
    c2.metric("Long",sum(1 for e in enhanced if e["type"]=="long"))
    c3.metric("Short",sum(1 for e in enhanced if e["type"]=="short"))
    c4.metric("P&L",f"₹{total_pnl:+,.2f}",delta_color="normal" if total_pnl>=0 else "inverse")

    st.dataframe(pd.DataFrame([{
        "Instrument":e["disp"],"Strike":e["strike"],"Option":e["right"],
        "Qty":e["qty"],"Position":e["type"].upper(),
        "Avg":f"₹{e['avg']:.2f}","LTP":f"₹{e['ltp']:.2f}",
        "P&L":f"₹{e['pnl']:+,.2f}","Close":PositionUtils.close_action(e["type"]).upper(),
    } for e in enhanced]), use_container_width=True, hide_index=True)

    if debug:
        with st.expander("🔧 Raw"):
            for e in enhanced: st.json(e["_raw"])

    st.markdown("---")
    for e in enhanced:
        em = "📈" if e["pnl"]>=0 else "📉"
        with st.expander(f"{em} {e['disp']} {e['strike']} {e['right']} | {'🟢 LONG' if e['type']=='long' else '🔴 SHORT'} | P&L: ₹{e['pnl']:+,.2f}"):
            c1,c2,c3=st.columns(3)
            c1.write(f"**Code:** {e['sc']}"); c1.write(f"**Exchange:** {e['exch']}"); c1.write(f"**Expiry:** {e['expiry']}")
            c2.write(f"**Position:** {e['type'].upper()}"); c2.write(f"**Qty:** {e['qty']}"); c2.write(f"**Avg:** ₹{e['avg']:.2f}")
            c3.write(f"**LTP:** ₹{e['ltp']:.2f}")
            color = "profit" if e["pnl"]>=0 else "loss"
            c3.markdown(f"<span class='{color}'>₹{e['pnl']:+,.2f}</span>",unsafe_allow_html=True)
            c3.write(f"**Close:** {PositionUtils.close_action(e['type']).upper()}")
            if st.button("🔄 Square Off",key=f"sq_{e['sc']}_{e['strike']}_{e['right']}",use_container_width=True):
                SessionManager.set_page("Square Off"); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER & MAIN
# ══════════════════════════════════════════════════════════════════════════════

PAGES = {
    "Dashboard": page_dashboard,
    "Option Chain": page_option_chain,
    "Sell Options": page_sell_options,
    "Square Off": page_square_off,
    "Orders & Trades": page_orders_trades,
    "Positions": page_positions,
}


def main():
    SessionManager.init()
    render_sidebar()

    st.markdown('<h1 class="main-header">📈 Breeze Options Trader</h1>', unsafe_allow_html=True)
    st.markdown("---")

    page = SessionManager.get_page()
    fn = PAGES.get(page, page_dashboard)

    if page in AUTH_REQUIRED and not SessionManager.is_authenticated():
        st.warning("🔒 Please login")
        st.info("👈 Enter credentials in sidebar")
        return

    fn()


if __name__ == "__main__":
    main()
