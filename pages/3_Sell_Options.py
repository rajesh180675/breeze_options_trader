"""
Sell Options Page - Sell Call/Put Options
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import time

import sys
sys.path.append('..')

from config import Config, SessionState
from utils import Utils
from session_manager import session_manager, notification_manager

# Page Config
st.set_page_config(
    page_title="Sell Options - Breeze Options",
    page_icon="💰",
    layout="wide"
)

# Initialize Session
SessionState.init_session_state()

# Custom CSS
st.markdown("""
<style>
    .sell-header {
        font-size: 2rem;
        font-weight: bold;
        color: #dc3545;
    }
    .order-form {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #dee2e6;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 1rem;
        border-radius: 5px;
        border-left: 4px solid #ffc107;
    }
    .info-box {
        background-color: #cce5ff;
        padding: 1rem;
        border-radius: 5px;
        border-left: 4px solid #004085;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<h1 class="sell-header">💰 Sell Options</h1>', unsafe_allow_html=True)
    
    notification_manager.show_messages()
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please login from the main page to place orders")
        if st.button("🏠 Go to Home"):
            st.switch_page("app.py")
        return
    
    client = st.session_state.breeze_client
    
    # Market Status Check
    if not Utils.is_market_open():
        st.warning(f"⚠️ {Utils.get_market_status()} - Orders may be queued")
    
    # Main Form
    st.subheader("📝 Order Details")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Instrument Selection")
        
        # Instrument
        instrument = st.selectbox(
            "Select Instrument",
            options=list(Config.INSTRUMENTS.keys()),
            index=list(Config.INSTRUMENTS.keys()).index(
                st.session_state.get('selected_instrument', 'NIFTY')
            ),
            key="sell_instrument",
            help="Choose the index to trade"
        )
        
        instrument_config = Config.INSTRUMENTS[instrument]
        
        st.info(f"""
        **{instrument_config['description']}**  
        - Exchange: {instrument_config['exchange']}
        - Lot Size: {instrument_config['lot_size']}
        - Strike Gap: {instrument_config['strike_gap']}
        """)
        
        # Expiry
        expiries = Config.get_next_expiries(instrument, 8)
        default_expiry_idx = 0
        if st.session_state.get('selected_expiry') in expiries:
            default_expiry_idx = expiries.index(st.session_state.selected_expiry)
        
        expiry = st.selectbox(
            "Expiry Date",
            options=expiries,
            index=default_expiry_idx,
            format_func=lambda x: Utils.format_expiry_date(x),
            key="sell_expiry"
        )
        
        # Option Type with tabs for visual clarity
        st.markdown("### Option Type")
        option_tab1, option_tab2 = st.tabs(["📈 CALL (CE)", "📉 PUT (PE)"])
        
        with option_tab1:
            if st.button("Select CALL", use_container_width=True, key="select_ce"):
                st.session_state.sell_option_type = "CE"
        
        with option_tab2:
            if st.button("Select PUT", use_container_width=True, key="select_pe"):
                st.session_state.sell_option_type = "PE"
        
        option_type = st.session_state.get('sell_option_type', 
                                           st.session_state.get('selected_option_type', 'CE'))
        
        st.success(f"**Selected: {'CALL (CE)' if option_type == 'CE' else 'PUT (PE)'}**")
    
    with col2:
        st.markdown("### Order Parameters")
        
        # Strike Price
        strike_price = st.number_input(
            "Strike Price",
            min_value=0,
            value=int(st.session_state.get('selected_strike', 0)),
            step=instrument_config["strike_gap"],
            key="sell_strike",
            help=f"Enter strike price (multiples of {instrument_config['strike_gap']})"
        )
        
        # Validate strike
        if strike_price % instrument_config["strike_gap"] != 0:
            st.warning(f"⚠️ Strike should be multiple of {instrument_config['strike_gap']}")
        
        # Quantity (Lots)
        lots = st.number_input(
            "Number of Lots",
            min_value=1,
            max_value=100,
            value=st.session_state.get('selected_lots', 1),
            key="sell_lots"
        )
        
        total_qty = lots * instrument_config["lot_size"]
        st.metric("Total Quantity", f"{total_qty}")
        st.caption(f"{lots} lots × {instrument_config['lot_size']} = {total_qty}")
        
        # Order Type
        st.markdown("### Order Type")
        order_type = st.radio(
            "Select Order Type",
            options=["Market", "Limit"],
            horizontal=True,
            key="sell_order_type"
        )
        
        # Limit Price
        limit_price = 0.0
        if order_type == "Limit":
            limit_price = st.number_input(
                "Limit Price (₹)",
                min_value=0.05,
                max_value=10000.0,
                value=100.0,
                step=0.05,
                format="%.2f",
                key="sell_limit_price"
            )
    
    st.markdown("---")
    
    # Quote and Margin Section
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📊 Live Quote")
        if st.button("Get Quote", use_container_width=True):
            if strike_price > 0:
                with st.spinner("Fetching quote..."):
                    quote = client.get_quotes(
                        stock_code=instrument_config["stock_code"],
                        exchange=instrument_config["exchange"],
                        expiry_date=expiry,
                        strike_price=strike_price,
                        option_type=option_type
                    )
                    
                    if quote["success"]:
                        quote_data = quote["data"].get("Success", [{}])
                        if quote_data:
                            q = quote_data[0] if isinstance(quote_data, list) else quote_data
                            st.session_state.current_quote = q
                            
                            st.success(f"""
                            **LTP:** ₹{q.get('ltp', 'N/A')}  
                            **Bid:** ₹{q.get('best_bid_price', 'N/A')}  
                            **Ask:** ₹{q.get('best_offer_price', 'N/A')}  
                            **Volume:** {q.get('volume', 'N/A')}
                            """)
                    else:
                        st.error(f"Failed: {quote.get('message', 'Unknown error')}")
            else:
                st.warning("Please enter a valid strike price")
    
    with col2:
        st.markdown("### 💰 Margin Required")
        if st.button("Calculate Margin", use_container_width=True):
            if strike_price > 0:
                with st.spinner("Calculating..."):
                    margin = client.get_margin_required(
                        stock_code=instrument_config["stock_code"],
                        exchange=instrument_config["exchange"],
                        expiry_date=expiry,
                        strike_price=strike_price,
                        option_type=option_type,
                        action="sell",
                        quantity=total_qty
                    )
                    
                    if margin["success"]:
                        margin_data = margin["data"].get("Success", {})
                        req_margin = margin_data.get("required_margin", "N/A")
                        st.info(f"**Required Margin:** ₹{req_margin}")
                    else:
                        st.warning("Could not calculate margin")
            else:
                st.warning("Please enter a valid strike price")
    
    with col3:
        st.markdown("### 📈 Premium Received")
        if 'current_quote' in st.session_state and strike_price > 0:
            ltp = float(st.session_state.current_quote.get('ltp', 0))
            premium = ltp * total_qty
            st.metric("Estimated Premium", f"₹{premium:,.2f}")
            st.caption("(Approximate, actual may vary)")
    
    st.markdown("---")
    
    # Order Summary and Confirmation
    st.subheader("📋 Order Summary")
    
    summary_col1, summary_col2 = st.columns(2)
    
    with summary_col1:
        st.markdown(f"""
        | Parameter | Value |
        |-----------|-------|
        | **Instrument** | {instrument} |
        | **Exchange** | {instrument_config['exchange']} |
        | **Expiry** | {Utils.format_expiry_date(expiry)} |
        | **Strike** | {strike_price} |
        | **Type** | {option_type} ({'Call' if option_type == 'CE' else 'Put'}) |
        """)
    
    with summary_col2:
        st.markdown(f"""
        | Parameter | Value |
        |-----------|-------|
        | **Action** | **SELL** |
        | **Lots** | {lots} |
        | **Quantity** | {total_qty} |
        | **Order Type** | {order_type} |
        | **Price** | {'Market' if order_type == 'Market' else f'₹{limit_price}'} |
        """)
    
    # Risk Warning
    st.markdown("---")
    st.markdown("""
    <div class="warning-box">
        <h4>⚠️ Important Risk Warning</h4>
        <p>
        <strong>Selling options carries unlimited risk potential.</strong><br>
        • Short Call: Unlimited loss if price rises significantly<br>
        • Short Put: Large loss if price falls significantly<br>
        • Margin requirements may increase with adverse price movement<br>
        • You may receive margin calls requiring additional funds
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Confirmation and Submit
    st.markdown("---")
    
    confirm = st.checkbox(
        "✅ I understand the risks involved in selling options and confirm all order details are correct",
        key="sell_confirm"
    )
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if confirm and strike_price > 0:
            button_label = f"🔴 SELL {instrument} {strike_price} {option_type} × {lots} lots"
            
            if st.button(button_label, type="primary", use_container_width=True):
                with st.spinner("Placing order..."):
                    # Place the order
                    if option_type == "CE":
                        result = client.sell_call(
                            stock_code=instrument_config["stock_code"],
                            exchange=instrument_config["exchange"],
                            expiry_date=expiry,
                            strike_price=strike_price,
                            quantity=total_qty,
                            order_type=order_type.lower(),
                            price=limit_price if order_type == "Limit" else 0
                        )
                    else:
                        result = client.sell_put(
                            stock_code=instrument_config["stock_code"],
                            exchange=instrument_config["exchange"],
                            expiry_date=expiry,
                            strike_price=strike_price,
                            quantity=total_qty,
                            order_type=order_type.lower(),
                            price=limit_price if order_type == "Limit" else 0
                        )
                    
                    if result["success"]:
                        order_data = result["data"].get("Success", {})
                        order_id = order_data.get("order_id", "N/A")
                        
                        # Log the order
                        session_manager.log_order({
                            "order_id": order_id,
                            "instrument": instrument,
                            "strike": strike_price,
                            "type": option_type,
                            "action": "SELL",
                            "quantity": total_qty,
                            "order_type": order_type,
                            "price": limit_price if order_type == "Limit" else "Market"
                        })
                        
                        st.success(f"""
                        ✅ **Order Placed Successfully!**
                        
                        **Order ID:** {order_id}  
                        **Status:** {order_data.get('message', 'Submitted')}
                        """)
                        st.balloons()
                        
                        # Navigation options
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("📋 View Orders"):
                                st.switch_page("pages/5_Orders.py")
                        with col2:
                            if st.button("📍 View Positions"):
                                st.switch_page("pages/6_Positions.py")
                    else:
                        st.error(f"""
                        ❌ **Order Failed!**
                        
                        **Error:** {result.get('message', 'Unknown error')}
                        """)
        elif not confirm:
            st.info("👆 Please confirm the risk acknowledgment to place the order")
        else:
            st.warning("⚠️ Please enter a valid strike price")
    
    # Quick Actions
    st.markdown("---")
    st.subheader("⚡ Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📈 View Option Chain", use_container_width=True):
            st.switch_page("pages/2_Option_Chain.py")
    
    with col2:
        if st.button("📍 View Positions", use_container_width=True):
            st.switch_page("pages/6_Positions.py")
    
    with col3:
        if st.button("🔄 Square Off", use_container_width=True):
            st.switch_page("pages/4_Square_Off.py")
    
    with col4:
        if st.button("📋 View Orders", use_container_width=True):
            st.switch_page("pages/5_Orders.py")


if __name__ == "__main__":
    main()
