# web_ui/bt_utils.py

import streamlit as st
import datetime
import sqlite3
import pandas as pd

import config
from src.strategies import STRATEGY_MAPPING_BT
from src.fetch_historical_data import fetch_and_store_historical_data
from src.market_calendar import is_market_working_day

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
    strategy_class = STRATEGY_MAPPING_BT[strategy_name]

    # --- INTELLIGENT RESOLUTION FETCHING (for parallel workers) ---
    strategy_instance_for_resolutions = strategy_class(symbols=[], resolutions=[primary_resolution])
    final_resolutions = strategy_instance_for_resolutions.get_required_resolutions()

    start_datetime = datetime.datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
    end_datetime = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")

    engine = BT_Engine(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        resolutions=final_resolutions
    )
    
    portfolio_result, last_prices, _ , _ = run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type)
    
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
    up-to-date and then runs the backtest.
    """
    from src.backtesting.bt_engine import BT_Engine # Local import

    try:
        data_is_sufficient = _check_data_availability(symbols, resolutions, start_dt, end_dt)

        if not data_is_sufficient:
            with st.spinner("Required data is missing or incomplete. Fetching updates... This may take a moment."):
                fetch_and_store_historical_data(symbols=symbols, resolutions=resolutions)
        st.success("Historical data is up-to-date.")

        engine = BT_Engine(start_datetime=start_dt, end_datetime=end_dt, resolutions=resolutions)
        return run_and_capture_backtest(engine, strategy_class, symbols, params, initial_cash, backtest_type)

    except Exception as e:
        st.error(f"An error occurred during the process: {e}")
        return None, None, None, None