"""
Square Off Page - Close existing positions
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
    page_title="Square Off - Breeze Options",
    page_icon="🔄",
    layout="wide"
)

# Initialize Session
SessionState.init_session_state()

# Custom CSS
st.markdown("""
<style>
    .squareoff-header {
        font-size: 2rem;
        font-weight: bold;
        color: #17a2b8;
    }
    .position-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        margin-bottom: 1rem;
    }
    .long-position {
        border-left: 4px solid #28a745;
    }
    .short-position {
        border-left: 4px solid #dc3545;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<h1 class="squareoff-header">🔄 Square Off Positions</h1>', unsafe_allow_html=True)
    
    notification_manager.show_messages()
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please login from the main page to manage positions")
        if st.button("🏠 Go to Home"):
            st.switch_page("app.py")
        return
    
    client = st.session_state.breeze_client
    
    # Refresh Button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Positions", use_container_width=True):
            st.rerun()
    
    # Fetch Positions
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    
    if not positions["success"]:
        st.error(f"Failed to load positions: {positions.get('message', 'Unknown error')}")
        return
    
    position_list = positions.get("data", {}).get("Success", [])
    
    # Filter active option positions
    active_positions = [
        p for p in position_list 
        if int(p.get("quantity", 0)) != 0 and p.get("product_type", "").lower() == "options"
    ]
    
    if not active_positions:
        st.info("📭 No open option positions to square off")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💰 Sell Options", use_container_width=True, type="primary"):
                st.switch_page("pages/3_Sell_Options.py")
        with col2:
            if st.button("📈 View Option Chain", use_container_width=True):
                st.switch_page("pages/2_Option_Chain.py")
        return
    
    # Position Summary
    st.subheader("📊 Position Summary")
    
    total_long = len([p for p in active_positions if int(p.get("quantity", 0)) > 0])
    total_short = len([p for p in active_positions if int(p.get("quantity", 0)) < 0])
    total_pnl = 0
    
    for pos in active_positions:
        qty = int(pos.get("quantity", 0))
        avg = float(pos.get("average_price", 0))
        ltp = float(pos.get("ltp", avg))
        
        if qty > 0:
            total_pnl += (ltp - avg) * qty
        else:
            total_pnl += (avg - ltp) * abs(qty)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Positions", len(active_positions))
    
    with col2:
        st.metric("Long Positions", total_long)
    
    with col3:
        st.metric("Short Positions", total_short)
    
    with col4:
        pnl_color = "normal" if total_pnl >= 0 else "inverse"
        st.metric("Total P&L", f"₹{total_pnl:,.2f}", delta_color=pnl_color)
    
    st.markdown("---")
    
    # Individual Position Square Off
    st.subheader("📍 Individual Square Off")
    
    # Create position display
    for idx, pos in enumerate(active_positions):
        qty = int(pos.get("quantity", 0))
        avg_price = float(pos.get("average_price", 0))
        ltp = float(pos.get("ltp", avg_price))
        stock_code = pos.get("stock_code", "")
        strike = pos.get("strike_price", "")
        right = pos.get("right", "").upper()
        expiry = pos.get("expiry_date", "")
        exchange = pos.get("exchange_code", "")
        
        position_type = "LONG" if qty > 0 else "SHORT"
        
        if qty > 0:
            pnl = (ltp - avg_price) * qty
        else:
            pnl = (avg_price - ltp) * abs(qty)
        
        pnl_display = f"₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}"
        pnl_color = "🟢" if pnl >= 0 else "🔴"
        
        with st.expander(
            f"{stock_code} {strike} {right} | {position_type} {abs(qty)} | {pnl_color} {pnl_display}",
            expanded=False
        ):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"""
                **Instrument:** {stock_code}  
                **Strike:** {strike}  
                **Type:** {right}  
                **Exchange:** {exchange}
                """)
            
            with col2:
                st.markdown(f"""
                **Position:** {position_type}  
                **Quantity:** {abs(qty)}  
                **Avg Price:** ₹{avg_price:.2f}  
                **LTP:** ₹{ltp:.2f}
                """)
            
            with col3:
                st.markdown(f"""
                **Expiry:** {expiry}  
                **P&L:** {pnl_display}  
                """)
            
            st.markdown("---")
            
            # Square off form
            col1, col2, col3 = st.columns(3)
            
            with col1:
                sq_qty = st.number_input(
                    "Quantity to Square Off",
                    min_value=1,
                    max_value=abs(qty),
                    value=abs(qty),
                    key=f"sq_qty_{idx}"
                )
            
            with col2:
                sq_order_type = st.radio(
                    "Order Type",
                    options=["Market", "Limit"],
                    horizontal=True,
                    key=f"sq_type_{idx}"
                )
            
            with col3:
                sq_limit_price = 0.0
                if sq_order_type == "Limit":
                    sq_limit_price = st.number_input(
                        "Limit Price",
                        min_value=0.05,
                        value=ltp,
                        step=0.05,
                        format="%.2f",
                        key=f"sq_price_{idx}"
                    )
            
            action_text = "BUY" if position_type == "SHORT" else "SELL"
            button_color = "primary" if position_type == "SHORT" else "secondary"
            
            if st.button(
                f"🔄 Square Off ({action_text} {sq_qty})",
                key=f"sq_btn_{idx}",
                type=button_color,
                use_container_width=True
            ):
                with st.spinner(f"Squaring off {stock_code} {strike} {right}..."):
                    result = client.square_off_position(
                        stock_code=stock_code,
                        exchange=exchange,
                        expiry_date=expiry,
                        strike_price=int(strike),
                        option_type=right,
                        quantity=sq_qty,
                        current_position="long" if position_type == "LONG" else "short",
                        order_type=sq_order_type.lower(),
                        price=sq_limit_price
                    )
                    
                    if result["success"]:
                        order_data = result["data"].get("Success", {})
                        st.success(f"✅ Position squared off! Order ID: {order_data.get('order_id', 'N/A')}")
                        
                        session_manager.log_order({
                            "order_id": order_data.get("order_id"),
                            "action": "SQUARE_OFF",
                            "instrument": stock_code,
                            "strike": strike,
                            "type": right,
                            "quantity": sq_qty
                        })
                        
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ Failed: {result.get('message', 'Unknown error')}")
    
    st.markdown("---")
    
    # Bulk Square Off
    st.subheader("⚡ Bulk Square Off")
    
    st.markdown("""
    <div style="background-color: #fff3cd; padding: 1rem; border-radius: 5px; border-left: 4px solid #ffc107;">
        <h4>⚠️ Warning</h4>
        <p>This will close ALL selected positions at market price. This action cannot be undone.</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Select positions to square off
        position_labels = [
            f"{p.get('stock_code')} {p.get('strike_price')} {p.get('right', '').upper()} - Qty: {p.get('quantity')}"
            for p in active_positions
        ]
        
        selected_positions = st.multiselect(
            "Select Positions to Square Off",
            options=range(len(position_labels)),
            format_func=lambda x: position_labels[x],
            default=list(range(len(position_labels)))
        )
    
    with col2:
        st.write("")
        st.write("")
        
        confirm_all = st.checkbox(
            "I confirm I want to square off the selected positions at market price",
            key="confirm_bulk"
        )
        
        if confirm_all and selected_positions:
            if st.button(
                f"🔴 SQUARE OFF {len(selected_positions)} POSITIONS",
                type="primary",
                use_container_width=True
            ):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                success_count = 0
                fail_count = 0
                
                for i, idx in enumerate(selected_positions):
                    pos = active_positions[idx]
                    qty = int(pos.get("quantity", 0))
                    position_type = "long" if qty > 0 else "short"
                    
                    status_text.text(f"Squaring off {pos.get('stock_code')} {pos.get('strike_price')}...")
                    
                    result = client.square_off_position(
                        stock_code=pos.get("stock_code"),
                        exchange=pos.get("exchange_code"),
                        expiry_date=pos.get("expiry_date"),
                        strike_price=int(pos.get("strike_price", 0)),
                        option_type=pos.get("right", "").upper(),
                        quantity=abs(qty),
                        current_position=position_type,
                        order_type="market"
                    )
                    
                    if result["success"]:
                        success_count += 1
                    else:
                        fail_count += 1
                    
                    progress_bar.progress((i + 1) / len(selected_positions))
                
                status_text.empty()
                
                if success_count > 0:
                    st.success(f"✅ Successfully squared off {success_count} position(s)")
                if fail_count > 0:
                    st.warning(f"⚠️ Failed to square off {fail_count} position(s)")
                
                time.sleep(2)
                st.rerun()
    
    # Navigation
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📍 View All Positions", use_container_width=True):
            st.switch_page("pages/6_Positions.py")
    
    with col2:
        if st.button("📋 View Orders", use_container_width=True):
            st.switch_page("pages/5_Orders.py")
    
    with col3:
        if st.button("💰 Sell More Options", use_container_width=True):
            st.switch_page("pages/3_Sell_Options.py")


if __name__ == "__main__":
    main()
