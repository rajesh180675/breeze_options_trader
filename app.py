"""
Breeze Options Trader - Main Application
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time

from app_config import Config, SessionState
from breeze_client import BreezeClientWrapper
from utils import Utils, OptionChainAnalyzer

st.set_page_config(
    page_title="Breeze Options Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main-header {font-size:2.5rem;font-weight:bold;color:#1f77b4;text-align:center;padding:1rem}
    .profit {color:#28a745;font-weight:bold}
    .loss {color:#dc3545;font-weight:bold}
    .stButton>button {width:100%}
</style>
""",
    unsafe_allow_html=True,
)

SessionState.init_session_state()


def main():
    st.markdown('<h1 class="main-header">📈 Breeze Options Trader</h1>', unsafe_allow_html=True)
    st.markdown("---")

    with st.sidebar:
        st.header("🔐 Authentication")
        if not st.session_state.authenticated:
            render_login_form()
        else:
            render_authenticated_sidebar()
        st.markdown("---")
        st.header("⚙️ Settings")
        render_settings()

    if not st.session_state.authenticated:
        render_welcome_page()
    else:
        render_main_dashboard()


def render_login_form():
    with st.form("login_form"):
        st.subheader("Enter API Credentials")
        api_key = st.text_input("API Key", value=st.session_state.api_key, type="password")
        api_secret = st.text_input("API Secret", value=st.session_state.api_secret, type="password")
        session_token = st.text_input("Session Token", value=st.session_state.session_token, type="password")
        st.markdown("💡 Get session token from ICICI Direct API section after login.")
        submitted = st.form_submit_button("🔑 Connect", use_container_width=True)
        if submitted:
            if api_key and api_secret and session_token:
                with st.spinner("Connecting..."):
                    client = BreezeClientWrapper(api_key, api_secret)
                    result = client.connect(session_token)
                    if result["success"]:
                        st.session_state.authenticated = True
                        st.session_state.breeze_client = client
                        st.session_state.api_key = api_key
                        st.session_state.api_secret = api_secret
                        st.session_state.session_token = session_token
                        st.success("✅ Connected!")
                        st.rerun()
                    else:
                        st.error(f"❌ {result['message']}")
            else:
                st.warning("⚠️ Fill all fields")


def render_authenticated_sidebar():
    st.success("✅ Connected")
    client = st.session_state.breeze_client
    info = client.get_customer_details()
    if info["success"]:
        name = info.get("data", {}).get("Success", {}).get("name", "User")
        st.info(f"👤 {name}")
    st.markdown(f"**{Utils.get_market_status()}**")
    funds = client.get_funds()
    if funds["success"]:
        avail = float(funds.get("data", {}).get("Success", {}).get("available_margin", 0))
        st.metric("Available Margin", Utils.format_currency(avail))
    if st.button("🔓 Disconnect", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.breeze_client = None
        st.rerun()


def render_settings():
    st.selectbox("Default Instrument", list(Config.INSTRUMENTS.keys()), key="selected_instrument")


def render_welcome_page():
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("### 📊 Real-time Data\n- Option chain\n- Live quotes")
    with c2:
        st.markdown("### 💰 Easy Trading\n- Sell options\n- Square off")
    with c3:
        st.markdown("### 🛡️ Risk Mgmt\n- Margin calc\n- P&L tracking")
    st.info("👈 Login via the sidebar to start trading.")


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


def render_dashboard_tab():
    client = st.session_state.breeze_client
    c1, c2 = st.columns([2, 1])
    with c1:
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="dash_instr")
    with c2:
        if st.button("🔄 Refresh"):
            st.rerun()
    cfg = Config.INSTRUMENTS[instrument]
    expiries = Config.get_next_expiries(instrument, 5)
    expiry = st.selectbox("Expiry", expiries, format_func=Utils.format_expiry_date)
    st.subheader(f"{instrument} Option Chain - {Utils.format_expiry_date(expiry)}")
    with st.spinner("Loading..."):
        oc = client.get_option_chain(cfg["stock_code"], cfg["exchange"], expiry)
    if oc["success"]:
        df = OptionChainAnalyzer.process_option_chain(oc["data"])
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("PCR", f"{OptionChainAnalyzer.calculate_pcr(df):.2f}")
            c2.metric("Max Pain", OptionChainAnalyzer.get_max_pain(df, cfg["strike_gap"]))
            c3.metric("Call OI", f"{df[df['right']=='Call']['open_interest'].sum():,.0f}")
            c4.metric("Put OI", f"{df[df['right']=='Put']['open_interest'].sum():,.0f}")
            st.dataframe(df[["strike_price", "right", "ltp", "open_interest", "volume"]], height=400)
        else:
            st.warning("No data")
    else:
        st.error(oc.get("message", "Error"))


def render_sell_options_tab():
    client = st.session_state.breeze_client
    st.subheader("💰 Sell Options")
    c1, c2 = st.columns(2)
    with c1:
        instrument = st.selectbox("Instrument", list(Config.INSTRUMENTS.keys()), key="sell_instr")
        cfg = Config.INSTRUMENTS[instrument]
        expiry = st.selectbox("Expiry", Config.get_next_expiries(instrument), format_func=Utils.format_expiry_date, key="sell_exp")
        opt = st.radio("Type", ["CE (Call)", "PE (Put)"], horizontal=True, key="sell_type")
        opt_code = "CE" if "CE" in opt else "PE"
    with c2:
        strike = st.number_input("Strike", min_value=0, step=cfg["strike_gap"], key="sell_strike")
        lots = st.number_input("Lots", min_value=1, max_value=100, value=1, key="sell_lots")
        qty = lots * cfg["lot_size"]
        st.info(f"Qty: {qty}")
        otype = st.radio("Order", ["Market", "Limit"], horizontal=True, key="sell_otype")
        price = st.number_input("Price", min_value=0.0, step=0.05, key="sell_price") if otype == "Limit" else 0.0
    st.warning("⚠️ Selling options has unlimited risk.")
    if st.checkbox("I understand the risks"):
        if st.button(f"🔴 SELL {opt_code}", type="primary", use_container_width=True):
            with st.spinner("Placing order..."):
                fn = client.sell_call if opt_code == "CE" else client.sell_put
                r = fn(cfg["stock_code"], cfg["exchange"], expiry, strike, qty, otype.lower(), price)
                if r["success"]:
                    st.success("✅ Order placed!")
                    st.balloons()
                else:
                    st.error(r.get("message", "Failed"))


def render_square_off_tab():
    client = st.session_state.breeze_client
    st.subheader("🔄 Square Off")
    with st.spinner("Loading positions..."):
        pos = client.get_portfolio_positions()
    if not pos["success"]:
        st.error(pos.get("message", "Error"))
        return
    plist = [p for p in pos.get("data", {}).get("Success", []) if p.get("product_type", "").lower() == "options" and int(p.get("quantity", 0)) != 0]
    if not plist:
        st.info("No open option positions")
        return
    st.success(f"{len(plist)} position(s)")
    df = pd.DataFrame(plist)
    st.dataframe(df[["stock_code", "strike_price", "right", "quantity", "ltp"]] if "ltp" in df.columns else df, use_container_width=True)
    labels = [f"{p['stock_code']} {p['strike_price']} {p['right']} Qty:{p['quantity']}" for p in plist]
    idx = st.selectbox("Select", range(len(labels)), format_func=lambda x: labels[x])
    p = plist[idx]
    qty = abs(int(p["quantity"]))
    ptype = "long" if int(p["quantity"]) > 0 else "short"
    sq_qty = st.number_input("Qty", 1, qty, qty, key="sq_qty")
    if st.button(f"🔄 Square Off ({'BUY' if ptype=='short' else 'SELL'})", type="primary", use_container_width=True):
        with st.spinner("Squaring off..."):
            r = client.square_off_position(p["stock_code"], p["exchange_code"], p["expiry_date"], int(p["strike_price"]), p["right"].upper(), sq_qty, ptype)
            if r["success"]:
                st.success("✅ Done!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(r.get("message", "Failed"))


def render_orders_tab():
    client = st.session_state.breeze_client
    st.subheader("📋 Orders")
    c1, c2 = st.columns(2)
    with c1:
        fd = st.date_input("From", datetime.now().date() - timedelta(days=7))
    with c2:
        td = st.date_input("To", datetime.now().date())
    if st.button("🔄 Refresh Orders"):
        st.rerun()
    with st.spinner("Loading..."):
        orders = client.get_order_list("", fd.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d"))
    if not orders["success"]:
        st.error(orders.get("message", "Error"))
        return
    olist = orders.get("data", {}).get("Success", [])
    if not olist:
        st.info("No orders")
        return
    st.dataframe(pd.DataFrame(olist), height=400)


def render_positions_tab():
    client = st.session_state.breeze_client
    st.subheader("📍 Positions")
    if st.button("🔄 Refresh Positions"):
        st.rerun()
    with st.spinner("Loading..."):
        pos = client.get_portfolio_positions()
    if not pos["success"]:
        st.error(pos.get("message", "Error"))
        return
    plist = pos.get("data", {}).get("Success", [])
    if not plist:
        st.info("No positions")
        return
    total_pnl = 0
    for p in plist:
        q = int(p.get("quantity", 0))
        if q != 0:
            avg, ltp = float(p.get("average_price", 0)), float(p.get("ltp", 0))
            pnl = (ltp - avg) * q if q > 0 else (avg - ltp) * abs(q)
            p["pnl"] = pnl
            total_pnl += pnl
    st.metric("Total P&L", f"₹{total_pnl:,.2f}")
    st.dataframe(pd.DataFrame(plist), height=400)


if __name__ == "__main__":
    main()
