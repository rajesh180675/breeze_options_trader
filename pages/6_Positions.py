"""
Positions Page - View and analyze positions
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import pytz

import sys
sys.path.append('..')

from config import Config, SessionState
from utils import Utils
from session_manager import session_manager, notification_manager

# Page Config
st.set_page_config(
    page_title="Positions - Breeze Options",
    page_icon="📍",
    layout="wide"
)

# Initialize Session
SessionState.init_session_state()

# Custom CSS
st.markdown("""
<style>
    .positions-header {
        font-size: 2rem;
        font-weight: bold;
        color: #28a745;
    }
    .profit { color: #28a745; font-weight: bold; }
    .loss { color: #dc3545; font-weight: bold; }
    .position-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<h1 class="positions-header">📍 Positions</h1>', unsafe_allow_html=True)
    
    notification_manager.show_messages()
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please login from the main page to view positions")
        if st.button("🏠 Go to Home"):
            st.switch_page("app.py")
        return
    
    client = st.session_state.breeze_client
    
    # Refresh
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Last updated: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')} IST")
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # Fetch Positions
    with st.spinner("Loading positions..."):
        positions = client.get_portfolio_positions()
    
    if not positions["success"]:
        st.error(f"Failed to load positions: {positions.get('message', 'Unknown error')}")
        return
    
    position_list = positions.get("data", {}).get("Success", [])
    
    # Separate active and closed positions
    active_positions = [p for p in position_list if int(p.get("quantity", 0)) != 0]
    closed_positions = [p for p in position_list if int(p.get("quantity", 0)) == 0]
    
    # Calculate totals
    total_pnl = 0
    total_investment = 0
    
    for pos in active_positions:
        qty = int(pos.get("quantity", 0))
        avg = float(pos.get("average_price", 0))
        ltp = float(pos.get("ltp", avg))
        
        if qty > 0:
            pnl = (ltp - avg) * qty
        else:
            pnl = (avg - ltp) * abs(qty)
        
        pos['calculated_pnl'] = pnl
        total_pnl += pnl
        total_investment += avg * abs(qty)
    
    # Summary Metrics
    st.subheader("📊 Portfolio Summary")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Active Positions", len(active_positions))
    
    with col2:
        long_count = len([p for p in active_positions if int(p.get("quantity", 0)) > 0])
        st.metric("Long", long_count)
    
    with col3:
        short_count = len([p for p in active_positions if int(p.get("quantity", 0)) < 0])
        st.metric("Short", short_count)
    
    with col4:
        pnl_color = "normal" if total_pnl >= 0 else "inverse"
        st.metric("Unrealized P&L", f"₹{total_pnl:,.2f}", delta_color=pnl_color)
    
    with col5:
        if total_investment > 0:
            pnl_percent = (total_pnl / total_investment) * 100
            st.metric("P&L %", f"{pnl_percent:.2f}%")
        else:
            st.metric("P&L %", "N/A")
    
    st.markdown("---")
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📍 Active Positions", "📊 Analytics", "📜 Closed Positions"])
    
    with tab1:
        if active_positions:
            st.subheader("Active Positions")
            
            # Create DataFrame
            df = pd.DataFrame(active_positions)
            
            # Format display columns
            display_data = []
            for pos in active_positions:
                qty = int(pos.get("quantity", 0))
                avg = float(pos.get("average_price", 0))
                ltp = float(pos.get("ltp", avg))
                pnl = pos.get('calculated_pnl', 0)
                
                display_data.append({
                    "Instrument": pos.get("stock_code"),
                    "Strike": pos.get("strike_price"),
                    "Type": pos.get("right", "").upper(),
                    "Expiry": pos.get("expiry_date"),
                    "Position": "LONG" if qty > 0 else "SHORT",
                    "Qty": abs(qty),
                    "Avg Price": f"₹{avg:.2f}",
                    "LTP": f"₹{ltp:.2f}",
                    "P&L": f"₹{pnl:,.2f}" if pnl >= 0 else f"-₹{abs(pnl):,.2f}",
                    "P&L %": f"{((ltp - avg) / avg * 100):.2f}%" if avg > 0 else "N/A"
                })
            
            df_display = pd.DataFrame(display_data)
            
            # Color code P&L
            st.dataframe(df_display, use_container_width=True, height=400)
            
            # Position Details Expanders
            st.subheader("Position Details")
            
            for idx, pos in enumerate(active_positions):
                qty = int(pos.get("quantity", 0))
                pnl = pos.get('calculated_pnl', 0)
                pnl_icon = "🟢" if pnl >= 0 else "🔴"
                
                with st.expander(
                    f"{pos.get('stock_code')} {pos.get('strike_price')} {pos.get('right', '').upper()} | "
                    f"{'LONG' if qty > 0 else 'SHORT'} {abs(qty)} | "
                    f"{pnl_icon} ₹{pnl:,.2f}"
                ):
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.markdown("**Position Info**")
                        st.write(f"Exchange: {pos.get('exchange_code')}")
                        st.write(f"Product: {pos.get('product_type')}")
                    
                    with col2:
                        st.markdown("**Price Info**")
                        st.write(f"Avg: ₹{float(pos.get('average_price', 0)):.2f}")
                        st.write(f"LTP: ₹{float(pos.get('ltp', 0)):.2f}")
                    
                    with col3:
                        st.markdown("**Greeks (Approx)**")
                        st.write(f"Delta: {pos.get('delta', 'N/A')}")
                        st.write(f"Theta: {pos.get('theta', 'N/A')}")
                    
                    with col4:
                        if st.button("🔄 Square Off", key=f"sq_{idx}"):
                            st.session_state.selected_position = pos
                            st.switch_page("pages/4_Square_Off.py")
        else:
            st.info("📭 No active positions")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💰 Sell Options", use_container_width=True, type="primary"):
                    st.switch_page("pages/3_Sell_Options.py")
            with col2:
                if st.button("📈 View Option Chain", use_container_width=True):
                    st.switch_page("pages/2_Option_Chain.py")
    
    with tab2:
        if active_positions:
            st.subheader("📊 Position Analytics")
            
            # P&L Distribution Chart
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### P&L by Position")
                
                pnl_data = []
                for pos in active_positions:
                    pnl_data.append({
                        "Position": f"{pos.get('stock_code')} {pos.get('strike_price')} {pos.get('right', '').upper()}",
                        "P&L": pos.get('calculated_pnl', 0)
                    })
                
                pnl_df = pd.DataFrame(pnl_data)
                
                fig = px.bar(
                    pnl_df,
                    x="Position",
                    y="P&L",
                    color="P&L",
                    color_continuous_scale=["red", "yellow", "green"],
                    title="P&L Distribution"
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("### Position Type Distribution")
                
                type_data = {
                    "Type": ["Long", "Short"],
                    "Count": [
                        len([p for p in active_positions if int(p.get("quantity", 0)) > 0]),
                        len([p for p in active_positions if int(p.get("quantity", 0)) < 0])
                    ]
                }
                
                fig_pie = px.pie(
                    values=type_data["Count"],
                    names=type_data["Type"],
                    title="Long vs Short Positions",
                    color_discrete_sequence=["#28a745", "#dc3545"]
                )
                fig_pie.update_layout(height=400)
                st.plotly_chart(fig_pie, use_container_width=True)
            
            # Instrument Distribution
            st.markdown("### Position by Instrument")
            
            instrument_data = {}
            for pos in active_positions:
                inst = pos.get("stock_code", "Unknown")
                if inst not in instrument_data:
                    instrument_data[inst] = 0
                instrument_data[inst] += 1
            
            if instrument_data:
                inst_df = pd.DataFrame({
                    "Instrument": list(instrument_data.keys()),
                    "Count": list(instrument_data.values())
                })
                
                fig_inst = px.bar(
                    inst_df,
                    x="Instrument",
                    y="Count",
                    title="Positions by Instrument"
                )
                st.plotly_chart(fig_inst, use_container_width=True)
            
            # Risk Metrics
            st.markdown("### Risk Metrics")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                max_profit_pos = max(active_positions, key=lambda x: x.get('calculated_pnl', 0))
                st.metric(
                    "Best Position",
                    f"{max_profit_pos.get('stock_code')} {max_profit_pos.get('strike_price')}",
                    f"₹{max_profit_pos.get('calculated_pnl', 0):,.2f}"
                )
            
            with col2:
                min_profit_pos = min(active_positions, key=lambda x: x.get('calculated_pnl', 0))
                st.metric(
                    "Worst Position",
                    f"{min_profit_pos.get('stock_code')} {min_profit_pos.get('strike_price')}",
                    f"₹{min_profit_pos.get('calculated_pnl', 0):,.2f}"
                )
            
            with col3:
                avg_pnl = total_pnl / len(active_positions) if active_positions else 0
                st.metric("Avg P&L per Position", f"₹{avg_pnl:,.2f}")
        else:
            st.info("No active positions to analyze")
    
    with tab3:
        st.subheader("📜 Closed Positions (Today)")
        
        if closed_positions:
            closed_df = pd.DataFrame(closed_positions)
            
            display_cols = ['stock_code', 'strike_price', 'right', 'average_price']
            available = [c for c in display_cols if c in closed_df.columns]
            
            st.dataframe(closed_df[available], use_container_width=True, height=300)
        else:
            st.info("No closed positions today")
    
    # Quick Actions
    st.markdown("---")
    st.subheader("⚡ Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔄 Square Off All", use_container_width=True):
            st.switch_page("pages/4_Square_Off.py")
    
    with col2:
        if st.button("💰 Sell Options", use_container_width=True):
            st.switch_page("pages/3_Sell_Options.py")
    
    with col3:
        if st.button("📋 View Orders", use_container_width=True):
            st.switch_page("pages/5_Orders.py")
    
    with col4:
        if st.button("📈 Option Chain", use_container_width=True):
            st.switch_page("pages/2_Option_Chain.py")


if __name__ == "__main__":
    main()
