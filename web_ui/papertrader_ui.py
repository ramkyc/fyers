# web_ui/pages/papertrader_ui.py


import streamlit as st
import time
import datetime
import json
import pandas as pd
import os

from src.live_config_manager import save_config, load_config, get_engine_status, start_engine, stop_engine
from src.strategies import STRATEGY_MAPPING
from src.market_calendar import is_market_working_day, NSE_MARKET_OPEN_TIME, NSE_MARKET_CLOSE_TIME
import config
from web_ui.utils import get_all_run_ids, load_log_data, analyze_live_run, load_live_positions

def render_page():
    """Renders the entire Live Paper Trading Monitor page."""

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


    # --- Main Panel UI ---
    st.header("Live Paper Trading Monitor")
    st.markdown("Configure, start, stop, and monitor the live paper trading engine.")

    st.subheader("Today's Trading Universe")
    all_symbols = sorted(list(set(current_config.get('symbols', []))))
    if all_symbols:
        st.info(f"**{len(all_symbols)} symbols are being traded today:** {', '.join(all_symbols)}")
    else:
        st.warning("The daily trading universe has not been generated yet. Please start the engine.")

    st.subheader("Engine Control")
    # Initialize session state if it doesn't exist
    if 'is_engine_running' not in st.session_state: st.session_state.is_engine_running = False

    # --- Get Real-time Status FIRST ---
    # This ensures the button states are always based on the latest information.
    status_message, is_running, current_run_id = get_engine_status()
    st.session_state.is_engine_running = is_running

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Start Live Engine", disabled=st.session_state.is_engine_running, use_container_width=True):
            with st.spinner("Attempting to start..."):
                success, message = start_engine()
                time.sleep(2) # Give the engine time to create its PID file
                st.rerun()
    with col2:
        if st.button("Stop Live Engine", disabled=not st.session_state.is_engine_running, use_container_width=True):
            with st.spinner("Sending stop signal..."):
                stop_engine()
                time.sleep(1)
                st.rerun()
    with col3:
        if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
            st.rerun()

    if is_running: st.success(f"**Status:** {status_message}")
    else: st.info(f"**Status:** {status_message}")

    st.markdown("---")

    st.markdown("---")
    st.subheader("Live Session Logs")
    
    # --- DEFINITIVE FIX for Disappearing Logs ---
    # The UI must be able to show the current session even if there are no historical logs.
    # 1. Get all run IDs (historical and current).
    all_run_ids = get_all_run_ids()
    
    # 2. If there are any runs (current or historical), render the log viewer.
    if all_run_ids:
        selected_run_id = st.selectbox("Select a Live Session to Analyze:", options=all_run_ids, key="live_run_selector")
        with st.spinner("Analyzing live session performance..."):
            live_metrics, trade_log_df = analyze_live_run(selected_run_id)
        
        if live_metrics:
            st.subheader("Performance Summary")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total P&L", f"₹{live_metrics['total_pnl']:,.2f}", f"{live_metrics['total_pnl'] / (live_metrics['initial_cash'] or 1):.2%}")
            col2.metric("Max Drawdown", f"{live_metrics['max_drawdown'] * 100:.2f}%")
            col3.metric("Sharpe Ratio", f"{live_metrics['sharpe_ratio']:.2f}")
            col4.metric("Win Rate", f"{live_metrics['win_rate']:.2%}")
            col5.metric("Profit Factor", f"{live_metrics['profit_factor']:.2f}")

            st.markdown("---")

            # --- Tabbed Interface for Logs and Positions ---
            tabs = st.tabs(["Open Positions", "Trade Log", "Strategy Debug Log"])

            # --- Open Positions Tab ---
            with tabs[0]:
                positions_df = load_live_positions(selected_run_id)
                if not positions_df.empty:
                    # Only show MTM for the currently active session
                    if selected_run_id == current_run_id:
                        total_mtm = positions_df['mtm'].sum()
                        st.metric("Total Mark-to-Market P&L", f"₹{total_mtm:,.2f}")
                    st.dataframe(positions_df, use_container_width=True)
                else:
                    st.info("No open positions found for this session.")

            # --- Trade Log Tab ---
            with tabs[1]:
                if trade_log_df is not None and not trade_log_df.empty:
                    st.dataframe(trade_log_df, use_container_width=True)
                else:
                    st.info("No trades have been executed in this session yet.")

            # --- Fetch and Parse All Logs Once ---
            debug_log_query = "SELECT timestamp, log_data FROM pt_live_debug_log WHERE run_id = ? ORDER BY timestamp DESC;"
            debug_log_df = load_log_data(debug_log_query, params=(selected_run_id,))
            
            if not debug_log_df.empty:
                parsed_logs = [json.loads(row['log_data']) for index, row in debug_log_df.iterrows()]
                # --- CORRECTED FILTERING LOGIC ---
                # Strategy logs are specifically marked with the message "Strategy Decision".
                strategy_decision_logs = [
                    log for log in parsed_logs 
                    if log.get('message') == "Strategy Decision" and 'data' in log and isinstance(log['data'], dict)
                ]
            else:
                strategy_decision_logs = []

            # --- Strategy Debug Log Tab ---
            with tabs[2]:
                if strategy_decision_logs:
                    # The 'data' key contains the structured log from the strategy
                    strategy_df = pd.DataFrame([log['data'] for log in strategy_decision_logs])
                    max_logs = st.slider("Number of recent decision logs to display", min_value=50, max_value=min(5000, len(strategy_df)), value=200, step=50, key="live_strat_log_slider")
                    st.dataframe(strategy_df.head(max_logs))
                else:
                    st.info("No strategy decision logs found for this session. The engine may be running but no strategy conditions have been met yet.")
    else:
        st.info("No active or historical trading sessions found. Start the engine to begin logging.")