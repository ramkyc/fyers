# web_ui/utils.py

import streamlit as st
import sqlite3
import pandas as pd
import os
import datetime
import json

import config
from src.strategies import STRATEGY_MAPPING

# This function must be defined at the top level to be pickleable by multiprocessing
def run_backtest_for_worker(args):
    """
    A self-contained function to run a single backtest.
    Designed to be executed in a separate process to enable parallelization.
    """
    start_date_str, end_date_str, db_file, resolutions, symbols, params, initial_cash, strategy_name, backtest_type = args

    # These imports are necessary inside the worker process
    from src.backtesting.engine import BacktestingEngine
    from src.reporting.performance_analyzer import PerformanceAnalyzer
    strategy_class = STRATEGY_MAPPING[strategy_name]
    start_datetime = datetime.datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")

    engine = BacktestingEngine(
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

@st.cache_data(ttl=60) # Cache for 1 minute
def load_log_data(query, params=()):
    """Loads log data from the trading log database."""
    if not os.path.exists(config.TRADING_DB_FILE):
        return pd.DataFrame()
    try:
        con = sqlite3.connect(f'file:{config.TRADING_DB_FILE}?mode=ro', uri=True)
        df = pd.read_sql_query(query, con, params=params)
        return df
    except (sqlite3.OperationalError, pd.io.sql.DatabaseError):
        st.info("Could not load log data. The database table may not exist yet.")
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

@st.cache_data(ttl=60)
def get_all_run_ids():
    """Fetches all unique run_ids from the trading log database."""
    if not os.path.exists(config.TRADING_DB_FILE):
        return []
    query = "SELECT DISTINCT run_id FROM paper_trades WHERE run_id IS NOT NULL ORDER BY timestamp DESC;"
    df = load_log_data(query)
    live_runs = [r for r in df['run_id'].tolist() if r.startswith('live_')]
    backtest_runs = [r for r in df['run_id'].tolist() if not r.startswith('live_')]
    return live_runs + backtest_runs

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