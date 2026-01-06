"""
Option Chain Analysis Page
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
from utils import Utils, OptionChainAnalyzer
from session_manager import session_manager, notification_manager

# Page Config
st.set_page_config(
    page_title="Option Chain - Breeze Options",
    page_icon="📈",
    layout="wide"
)

# Initialize Session
SessionState.init_session_state()

# Custom CSS
st.markdown("""
<style>
    .chain-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
    }
    .call-cell { background-color: #ffebee; }
    .put-cell { background-color: #e8f5e9; }
    .atm-row { background-color: #fff3e0 !important; }
</style>
""", unsafe_allow_html=True)


def main():
    st.markdown('<h1 class="chain-header">📈 Option Chain Analysis</h1>', unsafe_allow_html=True)
    
    notification_manager.show_messages()
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please login from the main page to access this feature")
        if st.button("🏠 Go to Home"):
            st.switch_page("app.py")
        return
    
    client = st.session_state.breeze_client
    
    # Instrument Selection
    st.subheader("🎯 Select Instrument")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        instrument = st.selectbox(
            "Instrument",
            options=list(Config.INSTRUMENTS.keys()),
            key="oc_instrument",
            help="Select the index for option chain"
        )
    
    instrument_config = Config.INSTRUMENTS[instrument]
    
    with col2:
        expiries = Config.get_next_expiries(instrument, 8)
        expiry = st.selectbox(
            "Expiry Date",
            options=expiries,
            format_func=lambda x: Utils.format_expiry_date(x),
            key="oc_expiry"
        )
    
    with col3:
        num_strikes = st.slider(
            "Strikes to Display",
            min_value=5,
            max_value=30,
            value=15,
            key="oc_strikes"
        )
    
    with col4:
        st.write("")  # Spacer
        st.write("")
        refresh = st.button("🔄 Refresh Chain", use_container_width=True)
    
    st.markdown("---")
    
    # Fetch Option Chain
    if refresh or 'option_chain_cache' not in st.session_state:
        with st.spinner("Loading option chain data..."):
            option_chain = client.get_option_chain(
                stock_code=instrument_config["stock_code"],
                exchange=instrument_config["exchange"],
                expiry_date=expiry
            )
            
            if option_chain["success"]:
                st.session_state.option_chain_cache = option_chain["data"]
                st.session_state.option_chain_time = datetime.now(pytz.timezone('Asia/Kolkata'))
            else:
                st.error(f"Failed to load: {option_chain.get('message', 'Unknown error')}")
                return
    
    # Process and Display
    if 'option_chain_cache' in st.session_state:
        df = OptionChainAnalyzer.process_option_chain(st.session_state.option_chain_cache)
        
        if not df.empty:
            # Analysis Metrics
            st.subheader("📊 Quick Analysis")
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            pcr = OptionChainAnalyzer.calculate_pcr(df)
            max_pain = OptionChainAnalyzer.get_max_pain(df, instrument_config["strike_gap"])
            
            calls = df[df['right'] == 'Call']
            puts = df[df['right'] == 'Put']
            
            with col1:
                pcr_delta = "High" if pcr > 1.2 else ("Low" if pcr < 0.8 else "Neutral")
                st.metric("PCR (OI)", f"{pcr:.2f}", delta=pcr_delta)
            
            with col2:
                st.metric("Max Pain", f"{max_pain:,}")
            
            with col3:
                call_oi = calls['open_interest'].sum() if 'open_interest' in calls.columns else 0
                st.metric("Call OI", f"{call_oi:,.0f}")
            
            with col4:
                put_oi = puts['open_interest'].sum() if 'open_interest' in puts.columns else 0
                st.metric("Put OI", f"{put_oi:,.0f}")
            
            with col5:
                if 'option_chain_time' in st.session_state:
                    time_str = st.session_state.option_chain_time.strftime("%H:%M:%S")
                    st.metric("Updated", time_str)
            
            st.markdown("---")
            
            # Visualization Tabs
            tab1, tab2, tab3 = st.tabs(["📊 OI Chart", "📈 Volume Chart", "📋 Chain Data"])
            
            with tab1:
                st.subheader("Open Interest Distribution")
                
                fig = go.Figure()
                
                calls_sorted = calls.sort_values('strike_price') if not calls.empty else pd.DataFrame()
                puts_sorted = puts.sort_values('strike_price') if not puts.empty else pd.DataFrame()
                
                if not calls_sorted.empty and 'open_interest' in calls_sorted.columns:
                    fig.add_trace(go.Bar(
                        x=calls_sorted['strike_price'],
                        y=calls_sorted['open_interest'],
                        name='Call OI',
                        marker_color='#ef5350',
                        opacity=0.8
                    ))
                
                if not puts_sorted.empty and 'open_interest' in puts_sorted.columns:
                    fig.add_trace(go.Bar(
                        x=puts_sorted['strike_price'],
                        y=puts_sorted['open_interest'],
                        name='Put OI',
                        marker_color='#66bb6a',
                        opacity=0.8
                    ))
                
                # Add max pain line
                fig.add_vline(
                    x=max_pain,
                    line_dash="dash",
                    line_color="orange",
                    annotation_text=f"Max Pain: {max_pain}"
                )
                
                fig.update_layout(
                    title=f'{instrument} Open Interest - Expiry: {Utils.format_expiry_date(expiry)}',
                    xaxis_title='Strike Price',
                    yaxis_title='Open Interest',
                    barmode='group',
                    height=500,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                st.subheader("Volume Distribution")
                
                fig_vol = go.Figure()
                
                if not calls_sorted.empty and 'volume' in calls_sorted.columns:
                    fig_vol.add_trace(go.Bar(
                        x=calls_sorted['strike_price'],
                        y=calls_sorted['volume'],
                        name='Call Volume',
                        marker_color='#ef5350'
                    ))
                
                if not puts_sorted.empty and 'volume' in puts_sorted.columns:
                    fig_vol.add_trace(go.Bar(
                        x=puts_sorted['strike_price'],
                        y=puts_sorted['volume'],
                        name='Put Volume',
                        marker_color='#66bb6a'
                    ))
                
                fig_vol.update_layout(
                    title=f'{instrument} Volume Distribution',
                    xaxis_title='Strike Price',
                    yaxis_title='Volume',
                    barmode='group',
                    height=500
                )
                
                st.plotly_chart(fig_vol, use_container_width=True)
            
            with tab3:
                st.subheader("Option Chain Data")
                
                view_type = st.radio(
                    "View",
                    options=["Combined", "Calls Only", "Puts Only"],
                    horizontal=True
                )
                
                if view_type == "Combined":
                    # Create combined view
                    call_cols = ['strike_price', 'ltp', 'open_interest', 'volume', 'best_bid_price', 'best_offer_price']
                    put_cols = ['strike_price', 'ltp', 'open_interest', 'volume', 'best_bid_price', 'best_offer_price']
                    
                    call_available = [c for c in call_cols if c in calls.columns]
                    put_available = [c for c in put_cols if c in puts.columns]
                    
                    if call_available and put_available:
                        calls_df = calls[call_available].copy()
                        calls_df.columns = ['Strike' if c == 'strike_price' else f'Call {c.replace("_", " ").title()}' for c in call_available]
                        
                        puts_df = puts[put_available].copy()
                        puts_df.columns = ['Strike' if c == 'strike_price' else f'Put {c.replace("_", " ").title()}' for c in put_available]
                        
                        combined = calls_df.merge(puts_df, on='Strike', how='outer').sort_values('Strike')
                        
                        st.dataframe(
                            combined,
                            use_container_width=True,
                            height=500
                        )
                
                elif view_type == "Calls Only":
                    display_cols = ['strike_price', 'ltp', 'open_interest', 'volume', 
                                   'best_bid_price', 'best_offer_price', 'ltp_percent_change']
                    available = [c for c in display_cols if c in calls.columns]
                    st.dataframe(
                        calls[available].sort_values('strike_price'),
                        use_container_width=True,
                        height=500
                    )
                
                else:
                    display_cols = ['strike_price', 'ltp', 'open_interest', 'volume',
                                   'best_bid_price', 'best_offer_price', 'ltp_percent_change']
                    available = [c for c in display_cols if c in puts.columns]
                    st.dataframe(
                        puts[available].sort_values('strike_price'),
                        use_container_width=True,
                        height=500
                    )
            
            # Quick Trade Section
            st.markdown("---")
            st.subheader("⚡ Quick Trade from Chain")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                strike_options = sorted(df['strike_price'].unique())
                selected_strike = st.selectbox(
                    "Select Strike",
                    options=strike_options,
                    key="quick_strike"
                )
            
            with col2:
                option_type = st.radio(
                    "Option Type",
                    options=["CE", "PE"],
                    horizontal=True,
                    key="quick_type"
                )
            
            with col3:
                lots = st.number_input(
                    "Lots",
                    min_value=1,
                    max_value=50,
                    value=1,
                    key="quick_lots"
                )
            
            with col4:
                st.write("")
                st.write("")
                if st.button("📤 Sell This Option", use_container_width=True, type="primary"):
                    st.session_state.selected_strike = selected_strike
                    st.session_state.selected_option_type = option_type
                    st.session_state.selected_lots = lots
                    st.session_state.selected_expiry = expiry
                    st.session_state.selected_instrument = instrument
                    st.switch_page("pages/3_Sell_Options.py")
        else:
            st.warning("No data available for the selected instrument and expiry")
    else:
        st.info("👆 Click 'Refresh Chain' to load option chain data")


if __name__ == "__main__":
    main()
