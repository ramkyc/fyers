# web_ui/pt_utils.py

import streamlit as st
import pandas as pd
import os
import json
import sqlite3

import config
from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.paper_trading.pt_portfolio import PT_Portfolio
from web_ui.utils import load_log_data # Import from the shared utils

@st.cache_data(ttl=60) # Cache for 1 minute
def get_live_tradeable_symbols():
    """Fetches the list of symbols prepared for today's live trading."""
    live_symbols_file = os.path.join(config.DATA_DIR, 'live_symbols.json')
    if not os.path.exists(live_symbols_file):
        st.warning("Live symbols file not found. Please ensure the daily data preparation script has run.")
        return [] # Return empty list, UI should handle this
    try:
        with open(live_symbols_file, 'r') as f:
            symbols = json.load(f)
        return sorted(symbols)
    except Exception as e:
        st.error(f"Error reading live symbols file: {e}")
        return []

@st.cache_data(ttl=1) # Cache for only 1 second for near real-time data
def load_live_incomplete_bar(symbol: str):
    """Loads the current incomplete bar for a symbol."""
    if not symbol: return None
    if not os.path.exists(config.LIVE_MARKET_DB_FILE): return None
    
    query = "SELECT * FROM live_incomplete_bars WHERE symbol = ?;"
    try:
        with sqlite3.connect(f'file:{config.LIVE_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            df = pd.read_sql_query(query, con, params=(symbol,))
            if not df.empty:
                return df.iloc[0].to_dict()
    except Exception:
        return None
    return None

@st.cache_data(ttl=5) # Cache for 5 seconds
def get_live_prices_from_cache() -> dict:
    """
    Fetches the most recent LTP for all symbols from the dedicated cache table.
    This is the source for real-time MTM calculations.
    """
    if not os.path.exists(config.LIVE_MARKET_DB_FILE):
        return {}
    try:
        with sqlite3.connect(f'file:{config.LIVE_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            df = pd.read_sql_query("SELECT symbol, ltp FROM live_ltp_cache", con)
            return df.set_index('symbol')['ltp'].to_dict()
    except Exception:
        return {}

@st.cache_data(ttl=5) # Cache the entire data fetch for 5 seconds
def get_live_session_data(is_running: bool, current_run_id: str):
    """
    A single, consolidated function to fetch all data needed for the live UI.
    This is cached to prevent database deadlocks on rapid refreshes.
    """
    # This function is now much simpler. It just orchestrates the analysis.
    # The heavy lifting of DB access is now centralized in PT_Portfolio.

    # 1. Analyze the primary run to get metrics and its trade log
    live_metrics, trade_log_df, open_positions_df = analyze_live_run(current_run_id)
    if live_metrics:
        live_metrics['run_id'] = current_run_id # Ensure run_id is in the metrics dict

    # Return data without the debug log
    return live_metrics, trade_log_df, open_positions_df


@st.cache_data(ttl=5) # Cache for 5 seconds to prevent hangs on rapid refreshes
def analyze_live_run(run_id: str):
    """
    Loads the data for a completed live run and calculates performance metrics.
    """
    # --- REFACTORED: Centralize data loading in the Portfolio ---
    # 1. Determine initial cash based on run type.
    is_live_run = run_id.startswith('live_') if run_id else True
    initial_cash = 10000000.0 if is_live_run else 5000000.0 # Default, will be refined if equity log exists

    # 2. Create a mock portfolio. Its __init__ will now automatically hydrate
    #    itself with all necessary data (positions, trades, equity curve) for this run_id.
    mock_portfolio = PT_Portfolio(initial_cash=initial_cash, run_id=run_id, enable_logging=False)

    # 3. Convert loaded data to DataFrames for analysis
    trade_log_df = pd.DataFrame(mock_portfolio.trades)
    open_positions_df = pd.DataFrame(list(mock_portfolio.positions.values()), index=mock_portfolio.positions.keys())
    if not open_positions_df.empty:
        open_positions_df.index.names = ['symbol', 'timeframe']
        open_positions_df = open_positions_df.reset_index()

    # 4. Build a complete last_prices dictionary for accurate MTM
    # 1. Get last prices from the trade log (for closed trades or recent entries)
    if not trade_log_df.empty:
        last_prices_from_trades = trade_log_df.groupby('symbol')['price'].last().to_dict()
    else:
        last_prices_from_trades = {}

    last_prices_from_positions = {}
    if not open_positions_df.empty:
        last_prices_from_positions = open_positions_df.set_index('symbol')['ltp'].to_dict()

    # 5. Get the absolute latest prices from the live cache
    live_prices_from_cache = get_live_prices_from_cache()

    # 6. Combine them, giving precedence in this order: Live Cache > Open Positions > Trade Log
    # This ensures we are using the most up-to-date price available for MTM calculation.
    last_prices = {**last_prices_from_trades, **last_prices_from_positions, **live_prices_from_cache}

    analyzer = PerformanceAnalyzer(mock_portfolio)
    return analyzer.calculate_metrics(last_prices), trade_log_df, open_positions_df