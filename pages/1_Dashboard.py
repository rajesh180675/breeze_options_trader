"""
Dashboard Page - Main Overview
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pytz

# Import from parent directory
import sys
sys.path.append('..')

from config import Config, SessionState
from breeze_client import BreezeClientWrapper
from utils import Utils, OptionChainAnalyzer
from session_manager import session_manager, notification_manager

# Page Config
st.set_page_config(
    page_title="Dashboard - Breeze Options",
    page_icon="📊",
    layout="wide"
)

# Initialize Session
SessionState.init_session_state()

# Custom CSS
st.markdown("""
<style>
    .dashboard-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .profit { color: #28a745; font-weight: bold; }
    .loss { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<h1 class="dashboard-header">📊 Trading Dashboard</h1>', unsafe_allow_html=True)
    
    # Show any pending notifications
    notification_manager.show_messages()
    
    # Check authentication
    if not st.session_state.authenticated:
        st.warning("⚠️ Please login from the main page to access the dashboard")
        st.info("""
        **To get started:**
        1. Go to the main page (Home)
        2. Enter your Breeze API credentials
        3. Click Connect
        """)
        
        if st.button("🏠 Go to Home Page"):
            st.switch_page("app.py")
        return
    
    client = st.session_state.breeze_client
    
    # Top Row - Key Metrics
    st.subheader("📈 Account Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Fetch funds
    funds = client.get_funds()
    funds_data = {}
    if funds["success"]:
        funds_data = funds.get("data", {}).get("Success", {})
    
    with col1:
        available = float(funds_data.get("available_margin", 0))
        st.metric(
            label="💰 Available Margin",
            value=Utils.format_currency(available),
            delta=None
        )
    
    with col2:
        used_margin = float(funds_data.get("utilized_margin", 0))
        st.metric(
            label="📊 Used Margin",
            value=Utils.format_currency(used_margin),
            delta=None
        )
    
    # Fetch positions for P&L
    positions = client.get_portfolio_positions()
    total_pnl = 0
    position_count = 0
    
    if positions["success"]:
        pos_list = positions.get("data", {}).get("Success", [])
        for pos in pos_list:
            qty = int(pos.get("quantity", 0))
            if qty != 0:
                position_count += 1
                avg_price = float(pos.get("average_price", 0))
                ltp = float(pos.get("ltp", avg_price))
                if qty > 0:
                    total_pnl += (ltp - avg_price) * qty
                else:
                    total_pnl += (avg_price - ltp) * abs(qty)
    
    with col3:
        delta_color = "normal" if total_pnl >= 0 else "inverse"
        st.metric(
            label="💹 Today's P&L",
            value=f"₹{total_pnl:,.2f}",
            delta=f"{total_pnl:+,.2f}",
            delta_color=delta_color
        )
    
    with col4:
        st.metric(
            label="📍 Open Positions",
            value=position_count,
            delta=None
        )
    
    st.markdown("---")
    
    # Market Status
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("🏪 Market Status")
        market_status = Utils.get_market_status()
        st.markdown(f"### {market_status}")
        
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        st.caption(f"Last updated: {now.strftime('%d-%b-%Y %H:%M:%S')} IST")
    
    with col2:
        if st.button("🔄 Refresh All Data", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    
    # Quick Actions
    st.subheader("⚡ Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("💰 Sell Call", use_container_width=True, type="primary"):
            st.session_state.selected_option_type = "CE"
            st.switch_page("pages/3_Sell_Options.py")
    
    with col2:
        if st.button("💰 Sell Put", use_container_width=True, type="primary"):
            st.session_state.selected_option_type = "PE"
            st.switch_page("pages/3_Sell_Options.py")
    
    with col3:
        if st.button("🔄 Square Off", use_container_width=True):
            st.switch_page("pages/4_Square_Off.py")
    
    with col4:
        if st.button("📈 Option Chain", use_container_width=True):
            st.switch_page("pages/2_Option_Chain.py")
    
    st.markdown("---")
    
    # Positions Summary
    st.subheader("📍 Current Positions")
    
    if positions["success"]:
        pos_list = positions.get("data", {}).get("Success", [])
        active_positions = [p for p in pos_list if int(p.get("quantity", 0)) != 0]
        
        if active_positions:
            # Create DataFrame
            df = pd.DataFrame(active_positions)
            
            # Select and rename columns
            display_cols = {
                'stock_code': 'Instrument',
                'strike_price': 'Strike',
                'right': 'Type',
                'quantity': 'Qty',
                'average_price': 'Avg Price',
                'ltp': 'LTP'
            }
            
            available_cols = [c for c in display_cols.keys() if c in df.columns]
            df_display = df[available_cols].rename(columns=display_cols)
            
            # Calculate P&L
            if 'Qty' in df_display.columns and 'Avg Price' in df_display.columns and 'LTP' in df_display.columns:
                df_display['P&L'] = df_display.apply(
                    lambda row: (float(row['LTP']) - float(row['Avg Price'])) * int(row['Qty'])
                    if int(row['Qty']) > 0
                    else (float(row['Avg Price']) - float(row['LTP'])) * abs(int(row['Qty'])),
                    axis=1
                )
                df_display['P&L'] = df_display['P&L'].apply(
                    lambda x: f"₹{x:,.2f}" if x >= 0 else f"-₹{abs(x):,.2f}"
                )
            
            st.dataframe(df_display, use_container_width=True, height=300)
        else:
            st.info("📭 No open positions")
    else:
        st.error("Failed to load positions")
    
    st.markdown("---")
    
    # Recent Orders
    st.subheader("📋 Recent Orders")
    
    orders = client.get_order_list(
        from_date=datetime.now().strftime("%Y-%m-%d"),
        to_date=datetime.now().strftime("%Y-%m-%d")
    )
    
    if orders["success"]:
        order_list = orders.get("data", {}).get("Success", [])
        
        if order_list:
            df_orders = pd.DataFrame(order_list[:10])  # Show last 10
            
            cols_to_show = ['order_id', 'stock_code', 'action', 'quantity', 'price', 'order_status']
            available = [c for c in cols_to_show if c in df_orders.columns]
            
            st.dataframe(df_orders[available], use_container_width=True, height=200)
        else:
            st.info("📭 No orders today")
    else:
        st.warning("Could not load orders")
    
    # Footer
    st.markdown("---")
    st.caption("💡 Tip: Use the sidebar to navigate between different sections")


if __name__ == "__main__":
    main()
