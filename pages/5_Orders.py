"""
Orders Page - View and manage orders
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz

import sys
sys.path.append('..')

from config import Config, SessionState
from utils import Utils
from session_manager import session_manager, notification_manager

# Page Config
st.set_page_config(
    page_title="Orders - Breeze Options",
    page_icon="📋",
    layout="wide"
)

# Initialize Session
SessionState.init_session_state()

# Custom CSS
st.markdown("""
<style>
    .orders-header {
        font-size: 2rem;
        font-weight: bold;
        color: #6c757d;
    }
    .status-complete { color: #28a745; font-weight: bold; }
    .status-pending { color: #ffc107; font-weight: bold; }
    .status-rejected { color: #dc3545; font-weight: bold; }
    .status-cancelled { color: #6c757d; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


def get_status_color(status):
    """Get color based on order status"""
    status_lower = status.lower() if status else ""
    if "complete" in status_lower or "executed" in status_lower:
        return "🟢"
    elif "pending" in status_lower or "open" in status_lower:
        return "🟡"
    elif "reject" in status_lower:
        return "🔴"
    elif "cancel" in status_lower:
        return "⚪"
    return "🔵"


def main():
    st.markdown('<h1 class="orders-header">📋 Order Management</h1>', unsafe_allow_html=True)
    
    notification_manager.show_messages()
    
    if not st.session_state.authenticated:
        st.warning("⚠️ Please login from the main page to view orders")
        if st.button("🏠 Go to Home"):
            st.switch_page("app.py")
        return
    
    client = st.session_state.breeze_client
    
    # Filters
    st.subheader("🔍 Filters")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        exchange_filter = st.selectbox(
            "Exchange",
            options=["All", "NFO", "BFO"],
            key="order_exchange_filter"
        )
    
    with col2:
        from_date = st.date_input(
            "From Date",
            value=datetime.now().date() - timedelta(days=7),
            key="order_from_date"
        )
    
    with col3:
        to_date = st.date_input(
            "To Date",
            value=datetime.now().date(),
            key="order_to_date"
        )
    
    with col4:
        status_filter = st.selectbox(
            "Status",
            options=["All", "Complete", "Pending", "Rejected", "Cancelled"],
            key="order_status_filter"
        )
    
    if st.button("🔄 Refresh Orders", use_container_width=True):
        st.rerun()
    
    st.markdown("---")
    
    # Fetch Orders
    with st.spinner("Loading orders..."):
        orders = client.get_order_list(
            exchange="" if exchange_filter == "All" else exchange_filter,
            from_date=from_date.strftime("%Y-%m-%d"),
            to_date=to_date.strftime("%Y-%m-%d")
        )
    
    if not orders["success"]:
        st.error(f"Failed to load orders: {orders.get('message', 'Unknown error')}")
        return
    
    order_list = orders.get("data", {}).get("Success", [])
    
    if not order_list:
        st.info("📭 No orders found for the selected period")
        return
    
    # Filter by status if needed
    if status_filter != "All":
        order_list = [
            o for o in order_list 
            if status_filter.lower() in o.get("order_status", "").lower()
        ]
    
    # Order Summary
    st.subheader("📊 Order Summary")
    
    total_orders = len(order_list)
    complete_orders = len([o for o in order_list if "complete" in o.get("order_status", "").lower()])
    pending_orders = len([o for o in order_list if "pending" in o.get("order_status", "").lower() or "open" in o.get("order_status", "").lower()])
    rejected_orders = len([o for o in order_list if "reject" in o.get("order_status", "").lower()])
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Orders", total_orders)
    
    with col2:
        st.metric("Complete", complete_orders)
    
    with col3:
        st.metric("Pending", pending_orders)
    
    with col4:
        st.metric("Rejected", rejected_orders)
    
    st.markdown("---")
    
    # Orders Table
    st.subheader("📝 Order List")
    
    # Create DataFrame
    df = pd.DataFrame(order_list)
    
    # Select and format columns
    display_cols = {
        'order_id': 'Order ID',
        'order_datetime': 'Time',
        'stock_code': 'Instrument',
        'strike_price': 'Strike',
        'right': 'Type',
        'action': 'Action',
        'quantity': 'Qty',
        'price': 'Price',
        'order_type': 'Order Type',
        'order_status': 'Status'
    }
    
    available_cols = [c for c in display_cols.keys() if c in df.columns]
    df_display = df[available_cols].rename(columns={c: display_cols[c] for c in available_cols})
    
    # Add status indicator
    if 'Status' in df_display.columns:
        df_display['Status'] = df_display['Status'].apply(
            lambda x: f"{get_status_color(x)} {x}"
        )
    
    st.dataframe(df_display, use_container_width=True, height=400)
    
    st.markdown("---")
    
    # Pending Order Actions
    pending_order_list = [
        o for o in order_list 
        if "pending" in o.get("order_status", "").lower() or "open" in o.get("order_status", "").lower()
    ]
    
    if pending_order_list:
        st.subheader("⚡ Pending Order Actions")
        
        order_options = [
            f"{o.get('order_id')} - {o.get('stock_code')} {o.get('strike_price')} {o.get('right')} {o.get('action')} {o.get('quantity')}"
            for o in pending_order_list
        ]
        
        selected_idx = st.selectbox(
            "Select Order",
            options=range(len(order_options)),
            format_func=lambda x: order_options[x],
            key="selected_order"
        )
        
        selected_order = pending_order_list[selected_idx]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Cancel Order")
            
            if st.button("❌ Cancel This Order", use_container_width=True, type="secondary"):
                with st.spinner("Cancelling order..."):
                    result = client.cancel_order(
                        order_id=selected_order.get("order_id"),
                        exchange=selected_order.get("exchange_code")
                    )
                    
                    if result["success"]:
                        st.success(f"✅ Order {selected_order.get('order_id')} cancelled successfully!")
                        session_manager.log_order({
                            "action": "CANCEL",
                            "order_id": selected_order.get("order_id")
                        })
                        st.rerun()
                    else:
                        st.error(f"❌ Failed: {result.get('message', 'Unknown error')}")
        
        with col2:
            st.markdown("### Modify Order")
            
            new_price = st.number_input(
                "New Price",
                min_value=0.0,
                value=float(selected_order.get("price", 0)),
                step=0.05,
                format="%.2f",
                key="modify_price"
            )
            
            new_qty = st.number_input(
                "New Quantity",
                min_value=1,
                value=int(selected_order.get("quantity", 0)),
                key="modify_qty"
            )
            
            if st.button("✏️ Modify Order", use_container_width=True):
                with st.spinner("Modifying order..."):
                    result = client.modify_order(
                        order_id=selected_order.get("order_id"),
                        exchange=selected_order.get("exchange_code"),
                        quantity=new_qty,
                        price=new_price
                    )
                    
                    if result["success"]:
                        st.success(f"✅ Order modified successfully!")
                        st.rerun()
                    else:
                        st.error(f"❌ Failed: {result.get('message', 'Unknown error')}")
    
    st.markdown("---")
    
    # Order Details Viewer
    st.subheader("🔍 Order Details")
    
    order_id_input = st.text_input(
        "Enter Order ID to view details",
        key="order_id_lookup"
    )
    
    if order_id_input:
        if st.button("🔍 Lookup Order"):
            with st.spinner("Fetching order details..."):
                # Find order in list first
                found_order = None
                for o in order_list:
                    if str(o.get("order_id")) == order_id_input:
                        found_order = o
                        break
                
                if found_order:
                    st.json(found_order)
                else:
                    st.warning("Order not found in current list")
    
    # Session Order History
    st.markdown("---")
    st.subheader("📜 Session Order History")
    
    order_history = session_manager.get_order_history()
    
    if order_history:
        hist_df = pd.DataFrame(order_history)
        st.dataframe(hist_df, use_container_width=True, height=200)
    else:
        st.info("No orders placed in this session")
    
    # Navigation
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📍 View Positions", use_container_width=True):
            st.switch_page("pages/6_Positions.py")
    
    with col2:
        if st.button("🔄 Square Off", use_container_width=True):
            st.switch_page("pages/4_Square_Off.py")
    
    with col3:
        if st.button("💰 Sell Options", use_container_width=True):
            st.switch_page("pages/3_Sell_Options.py")


if __name__ == "__main__":
    main()
