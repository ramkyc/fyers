# web_ui/pages/papertrader_ui.py

import streamlit as st
import time
import datetime

from src.live_config_manager import save_config, load_config, get_engine_status, start_engine, stop_engine
from src.strategies import STRATEGY_MAPPING
from src.market_calendar import is_market_working_day, NSE_MARKET_OPEN_TIME, NSE_MARKET_CLOSE_TIME
import config
from web_ui.utils import get_all_run_ids, load_live_portfolio_log, load_log_data, analyze_live_run, load_live_positions

def render_page():
    """Renders the entire Live Paper Trading Monitor page."""
    # --- Sidebar Configuration ---
    st.sidebar.header("Live Trading Configuration")
    current_config, _ = load_config()
    if current_config is None: current_config = {}

    with st.sidebar.form("live_config_form", clear_on_submit=False):
        st.subheader("System Status & Config")
        st.info(
            """
            **This is an automated research platform.**
            - **Universe:** Top 10 Nifty50 stocks & 8 ATM index options.
            - **Capital:** ₹100,000 per symbol/timeframe slot.
            - **Timeframes:** 1m, 5m, 15m, 30m, 60m.
            
            *The only user-configurable settings are the Trading Mode and the Strategy.*
            """
        )

        st.subheader("Trading Mode")
        paper_trade_type = st.radio(
            "Select Paper Trading Mode",
            options=('Intraday', 'Positional'),
            index=0 if current_config.get('paper_trade_type', 'Intraday') == 'Intraday' else 1,
            horizontal=True,
            label_visibility="collapsed"
        )
        st.subheader("Select Strategy")
        selected_strategy = st.selectbox(
            "Select Strategy",
            options=list(STRATEGY_MAPPING.keys()),
            index=list(STRATEGY_MAPPING.keys()).index(current_config.get('strategy', config.DEFAULT_LIVE_STRATEGY)),
            label_visibility="collapsed"
        )

        submitted = st.form_submit_button("Save Live Configuration", width='stretch')
        if submitted:
            new_config = {
                'paper_trade_type': paper_trade_type,
                'strategy': selected_strategy,
                # Explicitly set symbols to None to ensure any old, saved symbol list is purged.
                'symbols': None,
                # We no longer save symbols or params from the UI for live trading.
                # They are determined automatically by the backend.
            }
            success, message = save_config(new_config)
            if success: st.sidebar.success(message)
            else: st.sidebar.error(message)

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
    if col1.button("Start Live Engine", disabled=st.session_state.is_engine_running, width='stretch'):
        with st.spinner("Attempting to start..."):
            success, message = start_engine()
            time.sleep(2) # Give the engine time to create its PID file
            # The script will rerun automatically after the widget interaction.
    if col2.button("Stop Live Engine", disabled=not st.session_state.is_engine_running, width='stretch'):
        with st.spinner("Sending stop signal..."):
            stop_engine()
            # The stop_engine function now waits for termination, so a long sleep here is not needed.
            time.sleep(1)
            # The script will rerun automatically.
    if col3.button("Stop and Restart", disabled=not st.session_state.is_engine_running, width='stretch', type="primary"):
        with st.spinner("Restarting engine..."):
            stop_engine()
            success, message = start_engine()
            time.sleep(2) # Give the new engine time to start

    if is_running: st.success(f"**Status:** {status_message}")
    else: st.info(f"**Status:** {status_message}")

    st.markdown("---")

    # --- Auto-refreshing Fragment ---
    is_market_open_now = is_market_working_day(datetime.date.today()) and NSE_MARKET_OPEN_TIME <= datetime.datetime.now().time() <= NSE_MARKET_CLOSE_TIME
    refresh_interval = st.sidebar.slider("UI Refresh Interval (s)", 5, 60, 10, key="live_refresh_interval", help="How often to refresh the live data below.")
    should_refresh = is_market_open_now and st.session_state.is_engine_running

    # --- More Stable Auto-Refresh using Meta Tag ---
    if should_refresh:
        st.html(f"<meta http-equiv='refresh' content='{refresh_interval}'>")

    # --- Live Data Display ---
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Live Open Positions")
    
    live_positions_container = st.empty()

    # The `current_run_id` is now sourced directly from the engine status (PID file).
    if st.session_state.is_engine_running and current_run_id:
        positions_df = load_live_positions(current_run_id)

        # Calculate and display Total MTM
        if not positions_df.empty:
            total_mtm = positions_df['mtm'].sum()
            with col2:
                st.metric("Total MTM", f"₹{total_mtm:,.2f}")
            with live_positions_container:
                st.dataframe(positions_df, use_container_width=True)
        else:
            with col2:
                st.metric("Total MTM", "₹0.00")
    else:
        live_positions_container.info(
            "The live engine is currently stopped. Click 'Start Live Engine' to begin."
        )

    st.markdown("---")
    st.subheader("Live Session Logs")
    live_runs = [r for r in get_all_run_ids() if r.startswith('live_')]
    if live_runs:
        selected_run_id = st.selectbox("Select a Live Session to Analyze:", options=live_runs, key="live_run_selector")
        
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

            st.subheader("Trade Log")
            # The Equity Curve tab has been removed as requested.
            if trade_log_df is not None and not trade_log_df.empty:
                st.dataframe(trade_log_df, use_container_width=True)
            else:
                st.info("No trades have been executed in this session yet.")