"""
Breeze Options Trader - Main Application
ICICI Direct Breeze SDK Options Trading Platform
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time

# Import custom modules  ← CHANGED: app_config instead of config

from breeze_client import BreezeClientWrapper
from utils import Utils, OptionChainAnalyzer

# Page Configuration
st.set_page_config(
    page_title="Breeze Options Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem;
    }
    .status-connected { color: #28a745; font-weight: bold; }
    .status-disconnected { color: #dc3545; font-weight: bold; }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem; border-radius: 0.5rem; color: white;
    }
    .profit { color: #28a745; font-weight: bold; }
    .loss { color: #dc3545; font-weight: bold; }
    .stButton>button { width: 100%; }
    .order-sell { background-color: #dc3545; color: white; }
    .order-buy { background-color: #28a745; color: white; }
</style>
""", unsafe_allow_html=True)

# Initialize Session State
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
        api_key = st.text_input("API Key", value=st.session_state.api_key,
                                type="password", help="Your ICICI Direct Breeze API Key")
        api_secret = st.text_input("API Secret", value=st.session_state.api_secret,
                                   type="password", help="Your ICICI Direct Breeze API Secret")
        session_token = st.text_input("Session Token", value=st.session_state.session_token,
                                      type="password", help="Session token from ICICI Direct login")
        st.markdown("""
        💡 **How to get Session Token:**
        1. Login to [ICICI Direct](https://www.icicidirect.com/)
        2. Generate session token from API section
        3. Paste it above
        """)
        submitted = st.form_submit_button("🔑 Connect", use_container_width=True)
        if submitted:
            if api_key and api_secret and session_token:
                with st.spinner("Connecting to Breeze API..."):
                    client = BreezeClientWrapper(api_key, api_secret)
                    result = client.connect(session_token)
                    if result["success"]:
                        st.session_state.authenticated = True
                        st.session_state.breeze_client = client
                        st.session_state.api_key = api_key
                        st.session_state.api_secret = api_secret
                        st.session_state.session_token = session_token
                        st.success("✅ Connected successfully!")
                        st.rerun()
                    else:
                        st.error(f"❌ Connection failed: {result['message']}")
            else:
                st.warning("⚠️ Please fill all credentials")


def render_authenticated_sidebar():
    st.success("✅ Connected")
    client = st.session_state.breeze_client
    customer_info = client.get_customer_details()
    if customer_info["success"]:
        data = customer_info.get("data", {}).get("Success", {})
        st.info(f"👤 {data.get('name', 'User')}")
    st.markdown(f"**{Utils.get_market_status()}**")
    funds_info = client.get_funds()
    if funds_info["success"]:
        funds_data = funds_info.get("data", {}).get("Success", {})
        available = float(funds_data.get("available_margin", 0))
        st.metric("Available Margin", Utils.format_currency(available))
    if st.button("🔓 Disconnect", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.breeze_client = None
        st.rerun()


def render_settings():
    st.selectbox("Default Instrument", options=list(Config.INSTRUMENTS.keys()),
                 key="selected_instrument", help="Select default trading instrument")
    auto_refresh = st.checkbox("Auto Refresh", value=False, help="Automatically refresh data")
    if auto_refresh:
        st.slider("Refresh Interval (seconds)", min_value=5, max_value=60, value=10)


def render_welcome_page():
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 📊 Real-time Data\n- Live option chain\n- Real-time quotes\n- Greeks calculation")
    with col2:
        st.markdown("### 💰 Easy Trading\n- Sell Call/Put options\n- Quick square off\n- Position management")
    with col3:
        st.markdown("### 🛡️ Risk Management\n- Margin calculator\n- P&L tracking\n- Position limits")
    st.markdown("---")
    st.info("👈 **Please login using the sidebar to start trading**\n\n"
            "Trade NIFTY, BANKNIFTY, SENSEX, and other index options.\n"
            "Sell Call and Put options, square off positions, view option chain, track orders.")


def render_main_dashboard():
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard", "💰 Sell Options", "🔄 Square Off", "📋 Orders", "📍 Positions"])
    with tab1:
        render_dashboard_tab()
    with tab2:
        render_sell_options_tab()
    with tab3:
        render_square_off_tab()
    with tab4:
        render_orders_tab()
    with tab5:
        render_positions_tab()


def render_dashboard_tab():
    client = st.session_state.breeze_client
    col1, col2 = st.columns([2, 1])
    with col1:
        instrument = st.selectbox("Select Instrument",
                                  options=list(Config.INSTRUMENTS.keys()), key="dashboard_instrument")
    with col2:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
    instrument_config = Config.INSTRUMENTS[instrument]
    expiries = Config.get_next_expiries(instrument, 5)
    selected_expiry = st.selectbox("Select Expiry", options=expiries,
                                   format_func=lambda x: Utils.format_expiry_date(x))
    st.subheader(f"📈 {instrument} Option Chain - {Utils.format_expiry_date(selected_expiry)}")
    with st.spinner("Loading option chain..."):
        option_chain = client.get_option_chain(
            stock_code=instrument_config["stock_code"],
            exchange=instrument_config["exchange"], expiry_date=selected_expiry)
    if option_chain["success"]:
        df = OptionChainAnalyzer.process_option_chain(option_chain["data"])
        if not df.empty:
            col1, col2, col3, col4 = st.columns(4)
            pcr = OptionChainAnalyzer.calculate_pcr(df)
            max_pain = OptionChainAnalyzer.get_max_pain(df, instrument_config["strike_gap"])
            with col1:
                st.metric("Put-Call Ratio", f"{pcr:.2f}")
            with col2:
                st.metric("Max Pain", f"{max_pain}")
            with col3:
                st.metric("Total Call OI", f"{df[df['right']=='Call']['open_interest'].sum():,.0f}")
            with col4:
                st.metric("Total Put OI", f"{df[df['right']=='Put']['open_interest'].sum():,.0f}")
            st.dataframe(df[['strike_price','right','ltp','open_interest','volume',
                             'best_bid_price','best_offer_price']],
                         use_container_width=True, height=400)
        else:
            st.warning("No option chain data available")
    else:
        st.error(f"Failed to load option chain: {option_chain.get('message','Unknown error')}")


def render_sell_options_tab():
    client = st.session_state.breeze_client
    st.subheader("💰 Sell Options")
    col1, col2 = st.columns(2)
    with col1:
        instrument = st.selectbox("Instrument", options=list(Config.INSTRUMENTS.keys()), key="sell_instrument")
        instrument_config = Config.INSTRUMENTS[instrument]
        expiries = Config.get_next_expiries(instrument, 5)
        expiry = st.selectbox("Expiry Date", options=expiries,
                              format_func=lambda x: Utils.format_expiry_date(x), key="sell_expiry")
        option_type = st.radio("Option Type", options=["CE (Call)","PE (Put)"],
                               horizontal=True, key="sell_option_type")
        option_type_code = "CE" if "CE" in option_type else "PE"
    with col2:
        strike_price = st.number_input("Strike Price", min_value=0,
                                       step=instrument_config["strike_gap"], key="sell_strike")
        lots = st.number_input("Number of Lots", min_value=1, max_value=100, value=1, key="sell_lots")
        quantity = lots * instrument_config["lot_size"]
        st.info(f"Total Quantity: {quantity} ({lots} lots × {instrument_config['lot_size']})")
        order_type = st.radio("Order Type", options=["Market","Limit"],
                              horizontal=True, key="sell_order_type")
        limit_price = 0.0
        if order_type == "Limit":
            limit_price = st.number_input("Limit Price", min_value=0.0, step=0.05, key="sell_limit_price")
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Get Quote", use_container_width=True):
            with st.spinner("Fetching quote..."):
                quote = client.get_quotes(stock_code=instrument_config["stock_code"],
                    exchange=instrument_config["exchange"], expiry_date=expiry,
                    strike_price=strike_price, option_type=option_type_code)
                if quote["success"]:
                    qd = quote["data"].get("Success",[{}])[0]
                    st.success(f"**LTP:** ₹{qd.get('ltp','N/A')}  \n"
                               f"**Bid:** ₹{qd.get('best_bid_price','N/A')}  \n"
                               f"**Ask:** ₹{qd.get('best_offer_price','N/A')}")
                else:
                    st.error(f"Failed to get quote: {quote.get('message','Unknown error')}")
    with col2:
        if st.button("💰 Calculate Margin", use_container_width=True):
            with st.spinner("Calculating margin..."):
                margin = client.get_margin_required(stock_code=instrument_config["stock_code"],
                    exchange=instrument_config["exchange"], expiry_date=expiry,
                    strike_price=strike_price, option_type=option_type_code,
                    action="sell", quantity=quantity)
                if margin["success"]:
                    md = margin["data"].get("Success",{})
                    st.info(f"Required Margin: ₹{md.get('required_margin','N/A')}")
                else:
                    st.warning("Could not calculate margin")
    st.markdown("---")
    st.warning("⚠️ **Warning:** You are about to SELL an option. This has unlimited risk potential.")
    confirm = st.checkbox("I understand the risks and confirm the order details")
    if confirm:
        if st.button(f"🔴 SELL {option_type_code}", type="primary", use_container_width=True):
            with st.spinner("Placing order..."):
                sell_fn = client.sell_call if option_type_code=="CE" else client.sell_put
                result = sell_fn(stock_code=instrument_config["stock_code"],
                    exchange=instrument_config["exchange"], expiry_date=expiry,
                    strike_price=strike_price, quantity=quantity,
                    order_type=order_type.lower(), price=limit_price)
                if result["success"]:
                    od = result["data"].get("Success",{})
                    st.success(f"✅ Order placed successfully!\n\n"
                               f"**Order ID:** {od.get('order_id','N/A')}\n\n"
                               f"**Status:** {od.get('message','Submitted')}")
                    st.balloons()
                else:
                    st.error(f"❌ Order failed: {result.get('message','Unknown error')}")


def render_square_off_tab():
    client = st.session_state.breeze_client
    st.subheader("🔄 Square Off Positions")
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    if not positions["success"]:
        st.error(f"Failed to load positions: {positions.get('message','Unknown error')}")
        return
    position_list = positions.get("data",{}).get("Success",[])
    if not position_list:
        st.info("📭 No open positions to square off")
        return
    option_positions = [p for p in position_list
                        if p.get("product_type","").lower()=="options" and int(p.get("quantity",0))!=0]
    if not option_positions:
        st.info("📭 No open option positions")
        return
    st.success(f"Found {len(option_positions)} open option position(s)")
    df = pd.DataFrame(option_positions)
    display_cols = ['stock_code','expiry_date','strike_price','right','quantity','average_price','ltp']
    st.dataframe(df[[c for c in display_cols if c in df.columns]], use_container_width=True)
    st.markdown("---")
    st.subheader("Square Off Individual Position")
    labels = [f"{p['stock_code']} {p['strike_price']} {p['right']} - Qty: {p['quantity']}"
              for p in option_positions]
    sel = st.selectbox("Select Position", options=range(len(labels)), format_func=lambda x: labels[x])
    pos = option_positions[sel]
    qty = abs(int(pos.get("quantity",0)))
    position_type = "long" if int(pos.get("quantity",0))>0 else "short"
    col1, col2 = st.columns(2)
    with col1:
        sq_order_type = st.radio("Order Type", options=["Market","Limit"],
                                 horizontal=True, key="sq_order_type")
    with col2:
        sq_limit_price = 0.0
        if sq_order_type=="Limit":
            sq_limit_price = st.number_input("Limit Price", min_value=0.0, step=0.05, key="sq_limit_price")
    sq_qty = st.number_input("Quantity to Square Off", min_value=1, max_value=qty, value=qty, key="sq_qty")
    action_text = "BUY" if position_type=="short" else "SELL"
    if st.button(f"🔄 Square Off ({action_text})", type="primary", use_container_width=True):
        with st.spinner("Squaring off position..."):
            result = client.square_off_position(
                stock_code=pos.get("stock_code"), exchange=pos.get("exchange_code"),
                expiry_date=pos.get("expiry_date"), strike_price=int(pos.get("strike_price",0)),
                option_type=pos.get("right","").upper(), quantity=sq_qty,
                current_position=position_type, order_type=sq_order_type.lower(), price=sq_limit_price)
            if result["success"]:
                st.success("✅ Position squared off successfully!")
                time.sleep(1); st.rerun()
            else:
                st.error(f"❌ Square off failed: {result.get('message','Unknown error')}")
    st.markdown("---")
    st.subheader("⚡ Square Off All Positions")
    st.warning("⚠️ This will close ALL open option positions at market price!")
    if st.button("🔴 SQUARE OFF ALL", type="secondary", use_container_width=True):
        confirm_all = st.checkbox("I confirm I want to square off ALL positions")
        if confirm_all:
            with st.spinner("Squaring off all positions..."):
                results = client.square_off_all()
                sc = sum(1 for r in results if r.get("success",False))
                fc = len(results)-sc
                if sc: st.success(f"✅ Squared off {sc} position(s)")
                if fc: st.warning(f"⚠️ Failed to square off {fc} position(s)")
                time.sleep(1); st.rerun()


def render_orders_tab():
    client = st.session_state.breeze_client
    st.subheader("📋 Order Management")
    col1, col2, col3 = st.columns(3)
    with col1:
        exchange_filter = st.selectbox("Exchange", options=["All","NFO","BFO"], key="order_exchange")
    with col2:
        from_date = st.date_input("From Date", value=datetime.now().date()-timedelta(days=7), key="order_from")
    with col3:
        to_date = st.date_input("To Date", value=datetime.now().date(), key="order_to")
    if st.button("🔄 Refresh Orders", use_container_width=True):
        st.rerun()
    with st.spinner("Loading orders..."):
        orders = client.get_order_list(
            exchange="" if exchange_filter=="All" else exchange_filter,
            from_date=from_date.strftime("%Y-%m-%d"), to_date=to_date.strftime("%Y-%m-%d"))
    if not orders["success"]:
        st.error(f"Failed to load orders: {orders.get('message','Unknown error')}")
        return
    order_list = orders.get("data",{}).get("Success",[])
    if not order_list:
        st.info("📭 No orders found for the selected period")
        return
    st.dataframe(pd.DataFrame(order_list), use_container_width=True, height=400)
    st.markdown("---")
    st.subheader("Order Actions")
    pending = [o for o in order_list if o.get("order_status","").lower() in ["pending","open"]]
    if pending:
        olabels = [f"{o['order_id']} - {o['stock_code']} {o['action']} {o['quantity']}" for o in pending]
        idx = st.selectbox("Select Order", options=range(len(olabels)), format_func=lambda x: olabels[x])
        sel_order = pending[idx]
        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ Cancel Order", use_container_width=True):
                with st.spinner("Cancelling order..."):
                    r = client.cancel_order(order_id=sel_order["order_id"], exchange=sel_order["exchange_code"])
                    if r["success"]:
                        st.success("✅ Order cancelled!"); time.sleep(1); st.rerun()
                    else:
                        st.error(f"❌ Failed: {r.get('message','Unknown error')}")
        with col2:
            if st.button("✏️ Modify Order", use_container_width=True):
                new_price = st.number_input("New Price", min_value=0.0,
                    value=float(sel_order.get("price",0)), step=0.05)
                new_qty = st.number_input("New Quantity", min_value=1,
                    value=int(sel_order.get("quantity",0)))
                if st.button("💾 Save Modifications"):
                    r = client.modify_order(order_id=sel_order["order_id"],
                        exchange=sel_order["exchange_code"], quantity=new_qty, price=new_price)
                    if r["success"]:
                        st.success("✅ Order modified!"); time.sleep(1); st.rerun()
                    else:
                        st.error(f"❌ Failed: {r.get('message','Unknown error')}")
    else:
        st.info("No pending orders to modify/cancel")


def render_positions_tab():
    client = st.session_state.breeze_client
    st.subheader("📍 Current Positions")
    if st.button("🔄 Refresh Positions", use_container_width=True):
        st.rerun()
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    if not positions["success"]:
        st.error(f"Failed to load positions: {positions.get('message','Unknown error')}")
        return
    position_list = positions.get("data",{}).get("Success",[])
    if not position_list:
        st.info("📭 No open positions")
        return
    total_pnl = 0
    for pos in position_list:
        qty = int(pos.get("quantity",0))
        avg = float(pos.get("average_price",0))
        ltp = float(pos.get("ltp",0))
        if qty != 0:
            pnl = (ltp-avg)*qty if qty>0 else (avg-ltp)*abs(qty)
            pos["calculated_pnl"] = pnl
            total_pnl += pnl
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Positions", len([p for p in position_list if int(p.get("quantity",0))!=0]))
    with col2:
        st.metric("Long Positions", len([p for p in position_list if int(p.get("quantity",0))>0]))
    with col3:
        st.metric("Short Positions", len([p for p in position_list if int(p.get("quantity",0))<0]))
    with col4:
        st.metric("Total P&L", f"₹{total_pnl:,.2f}",
                   delta_color="normal" if total_pnl>=0 else "inverse")
    st.markdown("---")
    df = pd.DataFrame(position_list)
    if "calculated_pnl" in df.columns:
        df["P&L"] = df["calculated_pnl"].apply(
            lambda x: f"₹{x:,.2f}" if x>=0 else f"-₹{abs(x):,.2f}")
    st.dataframe(df, use_container_width=True, height=400)
    st.markdown("---")
    st.subheader("📊 Position Details")
    active = [p for p in position_list if int(p.get("quantity",0))!=0]
    for pos in active:
        with st.expander(f"{pos.get('stock_code')} {pos.get('strike_price')} "
                         f"{pos.get('right')} - Qty: {pos.get('quantity')}"):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write(f"**Exchange:** {pos.get('exchange_code')}")
                st.write(f"**Expiry:** {pos.get('expiry_date')}")
                st.write(f"**Strike:** {pos.get('strike_price')}")
            with c2:
                st.write(f"**Type:** {pos.get('right')}")
                st.write(f"**Quantity:** {pos.get('quantity')}")
                st.write(f"**Avg Price:** ₹{pos.get('average_price',0)}")
            with c3:
                st.write(f"**LTP:** ₹{pos.get('ltp',0)}")
                pnl = pos.get("calculated_pnl",0)
                st.write(f"**P&L:** {'₹' if pnl>=0 else '-₹'}{abs(pnl):,.2f}")


if __name__ == "__main__":
    main()
