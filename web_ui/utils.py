# web_ui/utils.py

import streamlit as st
import sqlite3
import pandas as pd
import os
import datetime
import json

import config
from src.strategies import STRATEGY_MAPPING

from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.paper_trading.pt_portfolio import PT_Portfolio
# This function must be defined at the top level to be pickleable by multiprocessing
def run_backtest_for_worker(args):
    """
    A self-contained function to run a single backtest.
    Designed to be executed in a separate process to enable parallelization.
    """
    start_date_str, end_date_str, db_file, resolutions, symbols, params, initial_cash, strategy_name, backtest_type = args

    # These imports are necessary inside the worker process
    from src.backtesting.bt_engine import BT_Engine
    from src.reporting.performance_analyzer import PerformanceAnalyzer
    strategy_class = STRATEGY_MAPPING[strategy_name]
    start_datetime = datetime.datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")

    engine = BT_Engine(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        db_file=db_file,
        resolutions=resolutions
    )
    
    portfolio_result, last_prices, _ = run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type)
    
    if portfolio_result and last_prices:
        analyzer = PerformanceAnalyzer(portfolio_result)
        metrics = analyzer.calculate_metrics(last_prices)
        metrics.update(params) # Add all params to the result for later joining
        return metrics
    return None

def run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type):
    """Runs a backtest and captures its stdout log."""
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        portfolio_result, last_prices, run_id = engine.run(strategy_class=strategy_class, symbols=symbols, params=params, initial_cash=initial_cash, backtest_type=backtest_type)
    backtest_log = f.getvalue()
    return portfolio_result, last_prices, backtest_log

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

@st.cache_data(ttl=600) # Cache for 10 minutes
def get_all_symbols():
    """Fetches all unique symbols from the historical data table."""
    if not os.path.exists(config.HISTORICAL_MARKET_DB_FILE):
        st.warning(f"Historical market data file not found at {config.HISTORICAL_MARKET_DB_FILE}. Please run `python src/fetch_historical_data.py` to generate it.")
        return []
    try:
        # Each function should create its own connection to ensure thread safety.
        with sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            query = "SELECT DISTINCT symbol FROM historical_data ORDER BY symbol;"
            df = pd.read_sql_query(query, con)
            return df['symbol'].tolist() if not df.empty else []
    except Exception as e:
        st.error(f"Error reading symbols from historical database: {e}")
        return []

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

    query = "SELECT DISTINCT run_id FROM paper_trades WHERE run_id IS NOT NULL ORDER BY timestamp DESC;"
    df = load_log_data(query)
    live_runs = [r for r in df['run_id'].tolist() if r.startswith('live_')]
    backtest_runs = [r for r in df['run_id'].tolist() if not r.startswith('live_')]
    
    # 3. Combine them, ensuring the active run is at the top and there are no duplicates
    all_runs = ([active_run_id] if active_run_id else []) + live_runs + backtest_runs
    # Use a dictionary to preserve order while removing duplicates
    return list(dict.fromkeys(all_runs))

@st.cache_data(ttl=10) # Cache for 10 seconds
def load_live_portfolio_log(run_id: str):
    """Loads the portfolio log for a specific live run ID."""
    if not run_id:
        return pd.DataFrame()
    query = "SELECT timestamp, value FROM portfolio_log WHERE run_id = ? ORDER BY timestamp ASC;"
    df = load_log_data(query, params=(run_id,))
    return df

@st.cache_data(ttl=60) # Cache for 1 minute
def get_live_tradeable_symbols():
    """Fetches the list of symbols prepared for today's live trading."""
    live_symbols_file = os.path.join(config.DATA_DIR, 'live_symbols.json')
    if not os.path.exists(live_symbols_file):
        st.warning("Live symbols file not found. Please ensure the daily data preparation script has run.")
        return get_all_symbols() # Fallback to all historical symbols
    try:
        with open(live_symbols_file, 'r') as f:
            symbols = json.load(f)
        return sorted(symbols)
    except Exception as e:
        st.error(f"Error reading live symbols file: {e}")
        return []

@st.cache_data(ttl=5) # Cache for 5 seconds
def load_live_positions(run_id: str):
    """Loads the current open positions for a specific live run ID."""
    if not run_id:
        return pd.DataFrame()
    query = "SELECT symbol, timeframe, quantity, avg_price, ltp, mtm, stop_loss, target1, target2, target3 FROM live_positions WHERE run_id = ? ORDER BY symbol, timeframe;"
    df = load_log_data(query, params=(run_id,))
    return df

@st.cache_data(ttl=5) # Cache for 5 seconds
def load_live_bar_history(symbol: str):
    """Loads the most recent bar history for a symbol from the live strategy data table."""
    if not symbol:
        return pd.DataFrame()
    # The live_strategy_data table is in the LIVE_MARKET_DB_FILE
    if not os.path.exists(config.LIVE_MARKET_DB_FILE):
        return pd.DataFrame()
    
    query = "SELECT timestamp, open, high, low, close, volume FROM live_strategy_data WHERE symbol = ? ORDER BY timestamp ASC;"
    
    try:
        with sqlite3.connect(f'file:{config.LIVE_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            df = pd.read_sql_query(query, con, params=(symbol,))
            return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=1) # Cache for only 1 second for near real-time data
def load_live_incomplete_bar(symbol: str):
    """Loads the current incomplete bar for a symbol."""
    if not symbol:
        return None
    if not os.path.exists(config.LIVE_MARKET_DB_FILE):
        return None
    
    query = "SELECT * FROM live_incomplete_bars WHERE symbol = ?;"
    try:
        with sqlite3.connect(f'file:{config.LIVE_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            df = pd.read_sql_query(query, con, params=(symbol,))
            if not df.empty:
                return df.iloc[0].to_dict()
    except Exception:
        return None
    return None

def analyze_live_run(run_id: str):
    """
    Loads the data for a completed live run and calculates performance metrics.
    """
    if not run_id:
        return None, None

    # 1. Load the trade log for the selected run
    trade_log_query = "SELECT * FROM paper_trades WHERE run_id = ? ORDER BY timestamp ASC;"
    trade_log_df = load_log_data(trade_log_query, params=(run_id,))
    if trade_log_df.empty:
        return None, None # No trades, no performance to analyze

    # 2. Load the equity curve for the selected run
    portfolio_log_df = load_live_portfolio_log(run_id)
    if portfolio_log_df.empty:
        return None, None # No equity curve, can't calculate drawdown/sharpe

    # --- CRITICAL FIX ---
    # The initial cash for a live run is a known, fixed value set in the trading_scheduler.
    # Using this fixed value is more reliable than trying to infer it from the first log entry.
    initial_cash_for_live_run = 10000000.0 # This must match the value in trading_scheduler.py

    # 3. Create a mock portfolio object to hold the data for the analyzer
    mock_portfolio = PT_Portfolio(initial_cash=initial_cash_for_live_run, enable_logging=False)
    mock_portfolio.trades = trade_log_df.to_dict('records')
    mock_portfolio.equity_curve = portfolio_log_df.to_dict('records')

    # 4. Determine last prices for unrealized P&L calculation
    last_prices = trade_log_df.groupby('symbol')['price'].last().to_dict()

    # 5. Analyze and return metrics
    analyzer = PerformanceAnalyzer(mock_portfolio)
    return analyzer.calculate_metrics(last_prices), trade_log_df