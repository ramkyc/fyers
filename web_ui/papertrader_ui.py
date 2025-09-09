# web_ui/pages/papertrader_ui.py

import streamlit as st
import time
import datetime

from src.live_config_manager import save_config, load_config, get_engine_status, start_engine, stop_engine
from src.strategies import STRATEGY_MAPPING
from src.market_calendar import is_market_working_day, NSE_MARKET_OPEN_TIME, NSE_MARKET_CLOSE_TIME
from web_ui.utils import get_live_tradeable_symbols, get_all_run_ids, load_live_portfolio_log, load_log_data, analyze_live_run

def render_page():
    """Renders the entire Live Paper Trading Monitor page."""
    # --- Sidebar Configuration ---
    st.sidebar.header("Live Trading Configuration")
    current_config, _ = load_config()
    if current_config is None: current_config = {}

    with st.sidebar.form("live_config_form", clear_on_submit=False):
        st.subheader("Strategy & Symbols")
        selected_strategy = st.selectbox(
            "Select Strategy",
            options=list(STRATEGY_MAPPING.keys()),
            index=list(STRATEGY_MAPPING.keys()).index(current_config.get('strategy', 'Simple MA Crossover'))
        )

        # Use the new function to get today's relevant symbols
        all_symbols = get_live_tradeable_symbols()
        selected_symbols = st.multiselect(
            "Select Symbols to Trade",
            options=all_symbols,
            default=current_config.get('symbols', [])
        )

        st.subheader("Strategy Parameters")
        live_params = {}
        if selected_strategy == "Simple MA Crossover":
            live_params['short_window'] = st.slider("Short Window", 1, 50, current_config.get('params', {}).get('short_window', 9), key="live_sma_sw")
            live_params['long_window'] = st.slider("Long Window", 10, 200, current_config.get('params', {}).get('long_window', 21), key="live_sma_lw")
        elif selected_strategy == "Opening Price Crossover":
            live_params['ema_fast'] = st.slider("EMA Fast Period", 2, 20, current_config.get('params', {}).get('ema_fast', 9), key="live_opc_ef")
            live_params['ema_slow'] = st.slider("EMA Slow Period", 10, 50, current_config.get('params', {}).get('ema_slow', 21), key="live_opc_es")
            st.markdown("###### Stop-Loss Settings")
            live_params['atr_period'] = st.slider("ATR Period", 5, 50, current_config.get('params', {}).get('atr_period', 14), key="live_opc_atr_p")
            live_params['atr_multiplier'] = st.number_input("ATR Multiplier", 1.0, 5.0, current_config.get('params', {}).get('atr_multiplier', 1.5), 0.1, key="live_opc_atr_m")
            st.markdown("###### Profit Target Settings")
            live_params['rr1'] = st.number_input("R:R Target 1", 0.1, 5.0, current_config.get('params', {}).get('rr1', 0.5), 0.1, key="live_opc_rr1")
            live_params['exit_pct1'] = st.slider("Exit % at T1", 10, 100, current_config.get('params', {}).get('exit_pct1', 50), 5, key="live_opc_pct1")
            live_params['rr2'] = st.number_input("R:R Target 2", 0.5, 10.0, current_config.get('params', {}).get('rr2', 1.5), 0.1, key="live_opc_rr2")
            live_params['exit_pct2'] = st.slider("Exit % at T2", 10, 100, current_config.get('params', {}).get('exit_pct2', 20), 5, key="live_opc_pct2")
            live_params['rr3'] = st.number_input("R:R Target 3", 1.0, 20.0, current_config.get('params', {}).get('rr3', 3.0), 0.1, key="live_opc_rr3")
            st.info("The remaining position will be sold at Target 3.")
        
        live_params['trade_value'] = st.number_input("Trade Value (INR)", min_value=1000, max_value=100000, value=current_config.get('params', {}).get('trade_value', 25000), step=1000, key="live_common_val")

        submitted = st.form_submit_button("Save Live Configuration", use_container_width=True)
        if submitted:
            new_config = {
                'strategy': selected_strategy,
                'symbols': selected_symbols,
                'params': live_params
            }
            success, message = save_config(new_config)
            if success: st.sidebar.success(message)
            else: st.sidebar.error(message)

    # --- Main Panel UI ---
    st.header("Live Paper Trading Monitor")
    st.markdown("Configure, start, stop, and monitor the live paper trading engine.")

    st.subheader("Engine Control")
    if 'is_engine_running' not in st.session_state:
        _, st.session_state.is_engine_running = get_engine_status()

    col1, col2, col3 = st.columns(3)
    if col1.button("Start Live Engine", disabled=st.session_state.is_engine_running, use_container_width=True):
        with st.spinner("Attempting to start..."):
            success, message = start_engine()
            st.session_state.is_engine_running = success
            st.rerun()
    if col2.button("Stop Live Engine", disabled=not st.session_state.is_engine_running, use_container_width=True):
        with st.spinner("Sending stop signal..."):
            stop_engine()
            st.session_state.is_engine_running = False
            time.sleep(2)
            st.rerun()
    if col3.button("Stop and Restart", disabled=not st.session_state.is_engine_running, use_container_width=True, type="primary"):
        with st.spinner("Restarting engine..."):
            stop_engine()
            time.sleep(3)
            start_engine()
            st.session_state.is_engine_running = True
            time.sleep(1)
            st.rerun()

    status_message, is_running = get_engine_status()
    st.session_state.is_engine_running = is_running
    if is_running: st.success(f"**Status:** {status_message}")
    else: st.info(f"**Status:** {status_message}")

    st.markdown("---")
    st.subheader("Live Portfolio Performance")
    live_chart_container = st.empty()
    
    st.markdown("---")
    st.subheader("Live Session Logs")
    live_runs = [r for r in get_all_run_ids() if r.startswith('live_')]
    if live_runs:
        selected_run_id = st.selectbox("Select a Live Session to Analyze:", options=live_runs, key="live_run_selector")
        
        # --- Performance Summary for Selected Live Run ---
        with st.spinner("Analyzing live session performance..."):
            live_metrics = analyze_live_run(selected_run_id)
        
        if live_metrics:
            st.subheader("Performance Summary")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total P&L", f"₹{live_metrics['total_pnl']:,.2f}", f"{live_metrics['total_pnl'] / (live_metrics['initial_cash'] or 1):.2%}")
            col2.metric("Max Drawdown", f"{live_metrics['max_drawdown'] * 100:.2f}%")
            col3.metric("Sharpe Ratio", f"{live_metrics['sharpe_ratio']:.2f}")
            col4.metric("Win Rate", f"{live_metrics['win_rate']:.2%}")
            col5.metric("Profit Factor", f"{live_metrics['profit_factor']:.2f}")
        
        st.subheader(f"Trade Log for Run: `{selected_run_id}`")
        trade_log_df = load_log_data("SELECT * FROM paper_trades WHERE run_id = ? ORDER BY timestamp DESC;", params=(selected_run_id,))
        st.dataframe(trade_log_df, use_container_width=True)

    # --- Auto-refreshing logic ---
    is_market_open_now = is_market_working_day(datetime.date.today()) and NSE_MARKET_OPEN_TIME <= datetime.datetime.now().time() <= NSE_MARKET_CLOSE_TIME
    if is_market_open_now and st.session_state.is_engine_running:
        refresh_interval = st.sidebar.slider("Auto-Refresh Interval (seconds)", 5, 60, 5, key="live_refresh_interval")
        
        with live_chart_container:
            if live_runs:
                portfolio_log_df = load_live_portfolio_log(live_runs[0])
                st.line_chart(portfolio_log_df.set_index('timestamp'))

        time.sleep(refresh_interval)
        st.rerun()