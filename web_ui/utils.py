# web_ui/utils.py

import streamlit as st
import pandas as pd
import os
import datetime
import json
import sqlite3

import config
from src.strategies import STRATEGY_MAPPING
from src.fetch_historical_data import fetch_and_store_historical_data, _build_fix_list
from src.market_calendar import is_market_working_day

from src.reporting.performance_analyzer import PerformanceAnalyzer
from src.paper_trading.pt_portfolio import PT_Portfolio
# This function must be defined at the top level to be pickleable by multiprocessing
def run_backtest_for_worker(args):
    """
    A self-contained function to run a single backtest.
    Designed to be executed in a separate process to enable parallelization.
    """
    start_date_str, end_date_str, primary_resolution, symbols, params, initial_cash, strategy_name, backtest_type = args

    # These imports are necessary inside the worker process
    from src.backtesting.bt_engine import BT_Engine
    from src.reporting.performance_analyzer import PerformanceAnalyzer
    strategy_class = STRATEGY_MAPPING[strategy_name]

    # --- INTELLIGENT RESOLUTION FETCHING (for parallel workers) ---
    # Instantiate the strategy to ask it what resolutions it needs,
    # instead of hardcoding rules in the UI. This mirrors the single-backtest logic.
    strategy_instance_for_resolutions = strategy_class(symbols=[], resolutions=[primary_resolution])
    final_resolutions = strategy_instance_for_resolutions.get_required_resolutions()

    start_datetime = datetime.datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")

    engine = BT_Engine(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        resolutions=final_resolutions
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
        portfolio_result, last_prices, run_id, debug_log = engine.run(strategy_class=strategy_class, symbols=symbols, params=params, initial_cash=initial_cash, backtest_type=backtest_type)
    backtest_log = f.getvalue()
    return portfolio_result, last_prices, backtest_log, debug_log

def _check_data_availability(symbols: list, resolutions: list, start_dt: datetime.datetime, end_dt: datetime.datetime) -> bool:
    """
    Checks if the required historical data for a backtest is present in the database.
    This is a simplified check focusing on the date range.
    """
    print("--- Checking data availability for backtest period ---")

    try:
        with sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True) as con:
            for symbol in symbols:
                for res in resolutions:
                    query = "SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM historical_data WHERE symbol = ? AND resolution = ?"
                    df = pd.read_sql_query(query, con, params=(symbol, res))
                    if df.empty or df.iloc[0]['min_ts'] is None:
                        print(f"  - Data missing for {symbol} ({res}). Triggering download.")
                        return False # Data does not exist at all

                    min_ts = pd.to_datetime(df.iloc[0]['min_ts'])
                    max_ts = pd.to_datetime(df.iloc[0]['max_ts'])

                    # Check every market working day in the backtest period
                    current = start_dt
                    while current <= end_dt:
                        if is_market_working_day(current.date()):
                            if not (min_ts <= current <= max_ts):
                                print(f"  - Data missing for {symbol} ({res}) on {current.date()}. Have [{min_ts} to {max_ts}]. Triggering download.")
                                return False
                        current += datetime.timedelta(days=1)
            print("--- All required data is available for market working days. Skipping download. ---")
            return True # All checks passed

    except Exception as e:
        print(f"Warning: Could not verify data availability due to an error: {e}. Proceeding with data fetch as a precaution.")
        return False

def run_backtest_with_data_update(strategy_class, symbols, start_dt, end_dt, resolutions, params, initial_cash, backtest_type):
    """
    A helper function for the Streamlit UI that first ensures historical data is
    up-to-date and then runs the backtest. This replaces the direct call to
    run_and_capture_backtest.

    Args:
        strategy_class: The strategy class to be tested.
        symbols (list): List of symbols for the backtest.
        start_dt (datetime): Start datetime of the backtest.
        end_dt (datetime): End datetime of the backtest.
        resolutions (list): List of resolutions for the backtest.
        params (dict): Strategy parameters.
        initial_cash (float): Initial cash for the portfolio.
        backtest_type (str): 'Positional' or 'Intraday'.

    Returns:
        The results from the backtesting engine's run method, plus the log.
    """
    from src.backtesting.bt_engine import BT_Engine # Local import

    try:
        # --- Step 1: Update Historical Data ---
        # First, check if the data for the requested period already exists.
        data_is_sufficient = _check_data_availability(symbols, resolutions, start_dt, end_dt)

        if not data_is_sufficient:
            with st.spinner("Required data is missing or incomplete. Fetching updates... This may take a moment."):
                fetch_and_store_historical_data(
                    symbols=symbols,
                    resolutions=resolutions
                )
        st.success("Historical data is up-to-date.")

        # --- Step 2: Run the Backtest (reusing the existing capture logic) ---
        engine = BT_Engine(start_datetime=start_dt, end_datetime=end_dt, db_file=config.HISTORICAL_MARKET_DB_FILE, resolutions=resolutions)
        return run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type) # Returns 4 items now

    except Exception as e:
        st.error(f"An error occurred during the process: {e}")
        return None, None, None, None

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
    Fetches all unique symbols from the SymbolManager.
    Uses Streamlit's caching to ensure this is only run once per session.
    """
    # This function will now be the single source of truth for the symbol list in the UI.
    # The @st.cache_data decorator ensures that SymbolManager() is only initialized
    # once, and the result is stored for the duration of the TTL.
    from src.symbol_manager import SymbolManager # Local import
    
    # The SymbolManager is a singleton; this call will either create it
    # or return the existing instance. The caching wrapper prevents even this
    # from being called more than once.
    sm = SymbolManager()
    return sm.get_all_symbols(include_indices=True, include_options=False)

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

    # 1. Determine which tables to query based on the run_id prefix
    if run_id.startswith('live_'):
        trade_log_query = "SELECT * FROM live_paper_trades WHERE run_id = ? ORDER BY timestamp ASC;"
        equity_curve_query = "SELECT * FROM pt_portfolio_log WHERE run_id = ? ORDER BY timestamp ASC;"
    else:
        trade_log_query = "SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY timestamp ASC;"
        equity_curve_query = "SELECT * FROM bt_portfolio_log WHERE run_id = ? ORDER BY timestamp ASC;"

    # 2. Load the trade log and portfolio log
    trade_log_df = load_log_data(trade_log_query, params=(run_id,))
    portfolio_log_df = load_log_data(equity_curve_query, params=(run_id,))

    if trade_log_df.empty and portfolio_log_df.empty:
        return None, None # No equity curve, can't calculate drawdown/sharpe

    # 3. Determine initial cash
    initial_cash = 10000000.0 if run_id.startswith('live_') else (portfolio_log_df['cash'].iloc[0] + portfolio_log_df['holdings'].iloc[0] if not portfolio_log_df.empty else 5000000.0)

    # 4. Create a mock portfolio object to hold the data for the analyzer
    mock_portfolio = PT_Portfolio(initial_cash=initial_cash, enable_logging=False)
    mock_portfolio.trades = trade_log_df.to_dict('records')
    mock_portfolio.equity_curve = portfolio_log_df.to_dict('records')

    # 5. Determine last prices for unrealized P&L calculation
    last_prices = trade_log_df.groupby('symbol')['price'].last().to_dict()

    # 6. Analyze and return metrics
    analyzer = PerformanceAnalyzer(mock_portfolio)
    return analyzer.calculate_metrics(last_prices), trade_log_df