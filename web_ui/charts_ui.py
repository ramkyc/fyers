# web_ui/charts_ui.py

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import time
import datetime

from src.live_config_manager import load_config, get_engine_status
from src.market_calendar import is_market_working_day, NSE_MARKET_OPEN_TIME, NSE_MARKET_CLOSE_TIME
from web_ui.utils import load_live_bar_history, load_live_incomplete_bar

def render_page():
    """Renders the Live Charts page."""
    st.header("Live Market Charts")
    st.markdown("This page displays live, updating OHLC charts for the symbols configured for paper trading.")

    current_config, msg = load_config()
    if not current_config:
        st.error(f"Could not load configuration: {msg}")
        return

    symbols = sorted(list(set(current_config.get('symbols', []))))

    if not symbols:
        st.info("No symbols are currently configured for paper trading. Please configure them on the 'Live Paper Trading Monitor' tab.")
        return

    # --- Auto-refreshing logic ---
    _, is_running, _ = get_engine_status()
    is_market_open_now = is_market_working_day(datetime.date.today()) and NSE_MARKET_OPEN_TIME <= datetime.datetime.now().time() <= NSE_MARKET_CLOSE_TIME
    should_refresh = is_market_open_now and is_running
    refresh_interval = st.sidebar.slider("Chart Refresh Interval (s)", 10, 120, 30, key="chart_refresh_interval", help="How often to refresh the live charts.")

    @st.fragment(run_every=f"{refresh_interval}s" if should_refresh else None)
    def display_live_charts():
        tabs = st.tabs(symbols)
        for i, symbol in enumerate(symbols):
            with tabs[i]:
                # 1. Load the history of completed bars
                df_history = load_live_bar_history(symbol)
                
                # 2. Load the current, incomplete bar
                incomplete_bar = load_live_incomplete_bar(symbol)
                
                # 3. Combine them for a seamless chart
                if incomplete_bar:
                    df_incomplete = pd.DataFrame([incomplete_bar])
                    df = pd.concat([df_history, df_incomplete], ignore_index=True)
                else:
                    df = df_history

                if not df.empty:
                    fig = go.Figure(data=[go.Candlestick(
                        x=df['timestamp'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close']
                    )])
                    fig.update_layout(
                        title=f'Live 1-Minute Chart for {symbol}',
                        xaxis_title='Time',
                        yaxis_title='Price',
                        xaxis_rangeslider_visible=False # A cleaner look for live charts
                    )
                    # Replaced deprecated 'use_container_width=True' with 'width="stretch"'.
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info(f"Waiting for live bar data for {symbol}...")

    display_live_charts()