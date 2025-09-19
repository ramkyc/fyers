# web_ui/pages/papertrader_ui.py

from st_autorefresh import st_autorefresh
import streamlit as st
import time
import datetime
import json
import pandas as pd
import os
 
from src.live_config_manager import save_config, load_config, get_engine_status, start_engine, stop_engine
from src.strategies import STRATEGY_MAPPING
import config
from web_ui.utils import get_all_run_ids # Shared
from web_ui.pt_utils import get_live_session_data # The new, consolidated data function

def render_page():
    """Renders the entire Live Paper Trading Monitor page.""" 

    # --- Auto-Refresh Control ---
    # Refresh every 5 seconds ONLY if the engine is running.
    if 'is_engine_running' in st.session_state and st.session_state.is_engine_running:
        st_autorefresh(interval=5 * 1000, key="live_page_refresher")

    # --- Get Real-time Status FIRST ---
    # This ensures the button states and default selections are always based on the latest information.
    status_message, is_running, current_run_id = get_engine_status()
    st.session_state.is_engine_running = is_running

    # --- Sidebar Configuration ---
    st.sidebar.header("Live Trading Configuration")
    current_config, _ = load_config()
    if current_config is None: current_config = {}

    # --- Determine the actual timeframes being used by the engine ---
    # This logic mirrors the trading_scheduler.py to ensure consistency.
    active_timeframes = current_config.get('timeframes', ['1', '5', '15', '30', '60'])
    timeframes_str = ', '.join([f"{tf}m" for tf in active_timeframes])

    # --- Display System Status & Config (Read-Only) ---
    st.sidebar.subheader("System Status & Config")
    strategy_name = current_config.get('strategy', 'N/A')
    trade_type = current_config.get('paper_trade_type', 'N/A')
    trade_value = current_config.get('params', {}).get('trade_value', 'N/A')

    info_message = f"""
    **This is an automated research platform.**
    - **Strategy:** `{strategy_name}`
    - **Mode:** `{trade_type}`
    - **Timeframes:** `{timeframes_str}`
    - **Capital/Slot:** `₹{trade_value:,.0f}`
    - **Universe:** All Nifty50 stocks.
    
    *Configuration is read from `pt_config_stocks.yaml` and cannot be changed from the dashboard.*
    """
    st.sidebar.info(info_message)

    # --- CONTEXT-AWARE LOG DISPLAY (Moved to Sidebar) ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Session Analysis")
    all_run_ids = get_all_run_ids()

    # Decide which run_id to show by default
    if is_running and current_run_id:
        default_run_id = current_run_id
    elif all_run_ids:
        default_run_id = all_run_ids[0]
    else:
        default_run_id = None

    selected_run_id = None
    if all_run_ids:
        selected_run_id = st.sidebar.selectbox("Select Session to Analyze:", options=all_run_ids, index=all_run_ids.index(default_run_id) if default_run_id in all_run_ids else 0, key="live_run_selector")

    # --- Main Panel UI ---
    st.title("Live Paper Trading Monitor")
    st.subheader("Engine Control")
    # Initialize session state if it doesn't exist
    if 'is_engine_running' not in st.session_state: st.session_state.is_engine_running = False

    # --- ENHANCEMENT: Place status on the same line as controls for a compact layout ---
    col1, col2, col3 = st.columns([2, 2, 3]) # Adjust column widths
    with col1:
        if st.button("Start Live Engine", disabled=st.session_state.is_engine_running, use_container_width=True):
            with st.spinner("Attempting to start..."):
                success, message = start_engine()
                time.sleep(2) # Give the engine time to create its PID file
                st.rerun()
        if st.button("Stop Live Engine", disabled=not st.session_state.is_engine_running, use_container_width=True):
            with st.spinner("Sending stop signal..."):
                stop_engine()
                time.sleep(1)
                st.rerun()
    with col3:
        if is_running: st.success(f"**Status:** {status_message}")
        else: st.info(f"**Status:** {status_message}")

    if selected_run_id:
        # --- OPTIMIZATION: Fetch data conditionally ---
        # Only call the live data function if we are viewing the currently running session.
        # For historical sessions, use a cached function (which we assume pt_utils will provide).
        # For now, we will just call the same function but this structure is key.
        # The function is now called *after* a session is selected, not before.
        is_viewing_live = is_running and (selected_run_id == current_run_id)
        live_metrics, trade_log_df, open_positions_df = get_live_session_data(is_viewing_live, selected_run_id)

        if live_metrics and selected_run_id == live_metrics.get('run_id'):
            st.subheader("Performance Summary")
            col1, col2, col3 = st.columns(3)
            # --- ENHANCEMENT: Display separated P&L for clarity ---
            col1.metric("Realized P&L", f"₹{live_metrics['realized_pnl']:,.2f}")
            col1.metric("Win Rate", f"{live_metrics['win_rate']:.2%}")
            col2.metric("Unrealized P&L (MTM)", f"₹{live_metrics['unrealized_pnl']:,.2f}")
            col2.metric("Profit Factor", f"{live_metrics['profit_factor']:.2f}")
            # For live sessions, Drawdown and Sharpe are not meaningful as we don't have a full equity curve.
            # They are correctly calculated for backtests.
            col3.metric("Max Drawdown", "N/A", help="Max Drawdown is only available for completed backtests.")
            col3.metric("Sharpe Ratio", "N/A", help="Sharpe Ratio is only available for completed backtests.")

            st.markdown("---")

            # --- Tabbed Interface for Logs and Positions ---
            tabs = st.tabs(["Open Positions", "Trade Log"])

            # --- Open Positions Tab ---
            with tabs[0]:
                if not open_positions_df.empty:
                    # The MTM metric is now in the main summary, so we just show the table here.
                    st.dataframe(open_positions_df, width='stretch')
                else:
                    st.info("No open positions found for this session.")

            # --- Trade Log Tab ---
            with tabs[1]:
                if trade_log_df is not None and not trade_log_df.empty:
                    st.dataframe(trade_log_df, width='stretch')
                else:
                    st.info("No trades have been executed in this session yet.")

    else:
        st.info("No active or historical trading sessions found. Start the engine to begin logging.")