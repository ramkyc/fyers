# web_ui/utils.py

import streamlit as st
import pandas as pd
import os
import datetime
import json
import sqlite3

import config
from src.fetch_historical_data import get_top_nifty_stocks

@st.cache_data(ttl=3600) # Cache for 1 hour
def get_market_time_options(interval_minutes=15):
    """Generates a list of time options within market hours."""
    times = []
    start = datetime.datetime.strptime("09:15", "%H:%M")
    end = datetime.datetime.strptime("15:30", "%H:%M")
    while start <= end:
        times.append(start.time())
        start += datetime.timedelta(minutes=interval_minutes)
    return times

@st.cache_data(ttl=5) # Cache for 5 seconds for live data responsiveness
def load_log_data(query, params=()):
    """Loads log data from the trading log database."""
    if not os.path.exists(config.TRADING_DB_FILE):
        return pd.DataFrame()
    try:
        # Increased timeout to handle potential write-locks from the engine
        con = sqlite3.connect(f'file:{config.TRADING_DB_FILE}?mode=ro', uri=True, timeout=10)
        df = pd.read_sql_query(query, con, params=params)
        return df
    except sqlite3.OperationalError as e:
        # Provide more specific feedback based on the error
        if "database is locked" in str(e):
            st.info("Database is busy, retrying on next refresh...")
        elif "no such table" in str(e):
            st.info("Could not load log data. The database table may not exist yet.")
        else:
            st.warning(f"A database error occurred: {e}")
        return pd.DataFrame()
    except pd.io.sql.DatabaseError as e: # Catch pandas-specific DB errors
        st.info(f"Could not load log data. The database table may not exist yet. ({e})")
        return pd.DataFrame()

@st.cache_data(ttl=3600) # Cache for 1 hour
def get_all_symbols():
    """
    Fetches the NIFTY 50 stocks directly. This is much faster than querying
    the historical database for distinct symbols.
    """
    print("Fetching NIFTY50 list for backtesting symbol dropdown...")
    # This is the known universe for our backtesting.
    # Fetching it directly is a significant performance optimization.
    return sorted(get_top_nifty_stocks(top_n=50))

@st.cache_data(ttl=10) # Cache for 10 seconds for better responsiveness
def get_all_run_ids():
    """
    Fetches all unique run_ids from the trading log database and prepends the
    currently active run_id if the engine is running.
    """
    from src.live_config_manager import get_engine_status # Local import to avoid circular dependencies

    # 1. Get the currently active run_id, if any
    _, is_running, active_run_id = get_engine_status()

    # 2. Get all historical run_ids from the database
    if not os.path.exists(config.TRADING_DB_FILE):
        return [active_run_id] if active_run_id else []

    # Query both tables to get all possible run IDs
    query_live = "SELECT DISTINCT run_id FROM live_paper_trades WHERE run_id IS NOT NULL ORDER BY timestamp DESC;"
    query_bt = "SELECT DISTINCT run_id FROM backtest_trades WHERE run_id IS NOT NULL ORDER BY timestamp DESC;"
    
    df_live = load_log_data(query_live)
    df_bt = load_log_data(query_bt)
    
    live_runs = df_live['run_id'].tolist() if not df_live.empty else []
    backtest_runs = df_bt['run_id'].tolist() if not df_bt.empty else []
    
    # 3. Combine them, ensuring the active run is at the top and there are no duplicates
    all_runs = ([active_run_id] if active_run_id else []) + live_runs + backtest_runs
    # Use a dictionary to preserve order while removing duplicates
    return list(dict.fromkeys(all_runs))