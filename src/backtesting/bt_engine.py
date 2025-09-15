# src/backtesting/bt_engine.py

import sqlite3
import pandas as pd
import numpy as np
import datetime
from collections import defaultdict

from market_calendar import get_market_close_time
# Use absolute imports from the 'src' root
from src.backtesting.bt_portfolio import BT_Portfolio
from src.backtesting.bt_oms import BT_OrderManager
from reporting.performance_analyzer import PerformanceAnalyzer
import config # config.py is now in the project root

class BT_Engine:
    """
    The core engine for running backtests on historical data.
    """
    def __init__(self, start_datetime: datetime.datetime, end_datetime: datetime.datetime, db_file: str, resolutions: list[str] = None):
        """_
        Initializes the BT_Engine.

        Args:
            start_datetime (datetime.datetime): The start datetime for the backtest.
            end_datetime (datetime.datetime): The end datetime for the backtest.
            db_file (str): The path to the SQLite database file.
            resolutions (list[str]): The data resolutions to use for the backtest (e.g., ["D", "60", "15"]).
        """
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.db_file = db_file
        self.resolutions = resolutions if resolutions is not None else ["D"]
        self.primary_resolution = self.resolutions[0] # The first resolution is considered primary for iteration
        self.all_loaded_data = {}
        self.bar_history = defaultdict(lambda: defaultdict(list)) # To maintain rolling history for strategies
        self.warmup_period = 100 # Number of bars to pre-load for indicators
        # Connect in read-only mode to prevent locking issues with other processes (like data fetchers).
        db_uri = f'file:{self.db_file}?mode=ro'
        self.con = sqlite3.connect(db_uri, uri=True)
        print("Backtesting Engine initialized.")

    def _load_data(self, symbols: list, resolutions: list) -> dict[str, pd.DataFrame]:
        """
        Loads historical data from the database for the specified symbols and date range
        across multiple resolutions.

        Returns:
            dict[str, pd.DataFrame]: A dictionary where keys are resolutions and values are DataFrames.
        """
        all_data = {}
        for resolution in resolutions:
            # To warm up indicators, we need to fetch data starting from BEFORE the user's selected start date.
            # We fetch `warmup_period` number of rows before the start_datetime.
            # This is done by querying for a larger set and then splitting it.
            # --- OPTIMIZATION: Define a more precise start date for the query. ---
            # Instead of loading all data, we load from a calculated start date that includes a buffer for indicator warm-up.
            start_dt_for_query = self.start_datetime - datetime.timedelta(days=30 if resolution != 'D' else 365)

            query = f"""
                SELECT timestamp, symbol, open, high, low, close, volume
                FROM historical_data
                WHERE symbol IN ({','.join(['?']*len(symbols))})
                AND resolution = ?
                AND timestamp BETWEEN ? AND ? -- This clause makes the loading efficient
                ORDER BY timestamp ASC;
                """
            params = symbols + [resolution, start_dt_for_query, self.end_datetime]
            df = pd.read_sql_query(query, self.con, params=params)
            
            # Ensure timestamp column is datetime and normalize to be timezone-naive
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['timestamp'] = df['timestamp'].dt.tz_localize(None) # Ensure no timezone info
                # Convert to Unix nanoseconds for robust indexing and comparison
                df['timestamp'] = df['timestamp'].astype(np.int64) // 10**9 # Convert to seconds for consistency

            # Set a MultiIndex for efficient grouping and vectorized operations
            if not df.empty:
                df = df.set_index(['timestamp', 'symbol'])
            print(f"Loaded {len(df)} rows of historical data for resolution {resolution}.")
            all_data[resolution] = df
        self.all_loaded_data = all_data # Store loaded data in the engine instance
        return all_data

    def run(self, strategy_class, symbols: list, params: dict, initial_cash=100000.0, backtest_type: str = 'Positional'):
        """
        Runs an event-driven backtest for a given strategy.

        Args:
            strategy_class: The class of the strategy to test (e.g., SMACrossoverStrategy).
            symbols (list): The list of symbols to include in the backtest.
            params (dict): The parameters for the strategy.
            initial_cash (float): The starting cash for the portfolio.
            backtest_type (str): The type of backtest ('Positional' or 'Intraday').
        """
        print(f"\n---" + "-" * 20 + f" Starting Backtest: {strategy_class.__name__} " + "-" * 20 + "---")
        print(f"Symbols: {symbols}")
        print(f"Parameters: {params}")
        print(f"Date Range: {self.start_datetime} to {self.end_datetime}")
        print(f"Resolutions: {self.resolutions}")
        print(f"Initial Cash: {initial_cash:,.2f}")
        print("-" * 70)

        # 1. Load historical data
        self._load_data(symbols, self.resolutions)

        # --- NEW: Pre-populate bar history for warm-up ---
        start_timestamp_seconds = int(self.start_datetime.timestamp())
        for res, df in self.all_loaded_data.items():
            if df.empty: continue
            # Get all data before the official start time for warm-up
            warmup_df = df[df.index.get_level_values('timestamp') < start_timestamp_seconds]
            for symbol in symbols:
                symbol_warmup_df = warmup_df[warmup_df.index.get_level_values('symbol') == symbol]
                # Take the last N rows for the warm-up period
                symbol_warmup_df = symbol_warmup_df.tail(self.warmup_period)
                self.bar_history[res][symbol] = symbol_warmup_df.reset_index().to_dict('records')
        print("Bar history has been warmed up with pre-backtest data.")
        
        # Ensure primary resolution data is available
        if self.primary_resolution not in self.all_loaded_data or self.all_loaded_data[self.primary_resolution].empty:
            print(f"No data found for the primary resolution ({self.primary_resolution}) and given symbols/date range. Aborting backtest.")
            return None, None, None, [] # Return 4 values to match the expected tuple

        primary_resolution_data = self.all_loaded_data[self.primary_resolution]
        # Filter the primary data to only iterate over the user-defined backtest period
        primary_resolution_data = primary_resolution_data[primary_resolution_data.index.get_level_values('timestamp') >= start_timestamp_seconds]
        # DEBUG: Print number of rows and sample after filtering
        print(f"[DEBUG] primary_resolution_data rows after filtering: {len(primary_resolution_data)}")
        if not primary_resolution_data.empty:
            print("[DEBUG] Sample rows after filtering:")
            print(primary_resolution_data.head())
        else:
            print("[DEBUG] primary_resolution_data is empty after filtering. No data to backtest.")


        # Generate a unique ID for this backtest run to isolate its logs
        timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        strategy_name_short = strategy_class.__name__.replace("Strategy", "")
        # Limit symbols in the name to avoid excessively long run_ids
        symbols_str = "-".join(s.replace("NSE:", "").replace("-EQ", "") for s in symbols[:2])
        if len(symbols) > 2:
            symbols_str += f"_{len(symbols)-2}more"
        
        # Construct the new human-readable run_id
        run_id = f"bt_{timestamp_str}_{strategy_name_short}_{symbols_str}"
        print(f"Backtest Run ID: {run_id}")

        # 2. Initialize the portfolio and OrderManager
        # Each backtest gets a fresh, isolated portfolio instance.
        portfolio = BT_Portfolio(initial_cash=initial_cash, run_id=run_id)
        oms = BT_OrderManager(portfolio, run_id=run_id)
        strategy = strategy_class(symbols=symbols, portfolio=portfolio, order_manager=oms, params=params, resolutions=self.resolutions)

        # --- Intraday State Management ---
        market_close_time = get_market_close_time(datetime.date.today()).time()
        intraday_exit_time = (datetime.datetime.combine(datetime.date.today(), market_close_time) - datetime.timedelta(minutes=16)).time()
        intraday_positions_closed_today = set()
        last_processed_date = None

        print("--- Backtest Log ---")
        # 3. Event Loop: Iterate through each timestamp in the historical data
        # This simulates the passage of time, candle by candle.
        for timestamp_ns in primary_resolution_data.index.get_level_values('timestamp').unique().sort_values():
            # Convert nanosecond timestamp back to datetime for strategy and logging
            timestamp = pd.to_datetime(timestamp_ns, unit='s') # Convert from seconds to datetime

            current_date = timestamp.date()
            if last_processed_date and current_date > last_processed_date:
                intraday_positions_closed_today.clear()
            last_processed_date = current_date

            # Prepare market data for all resolutions for the current timestamp
            current_market_data_all_resolutions = {}
            for res in self.resolutions:
                res_data_df = self.all_loaded_data[res]
                res_group = pd.DataFrame()

                if not res_data_df.empty:
                    # For the primary (iterating) resolution, we do an exact timestamp match.
                    if res == self.primary_resolution:
                        try:
                            res_group = res_data_df.xs(timestamp_ns, level='timestamp', drop_level=False)
                        except KeyError:
                            pass # No data for this exact timestamp
                    # For secondary resolutions (like 'D' when primary is '30'), we find the last available data point.
                    else:
                        # Find the index of the last row where the timestamp is <= current timestamp
                        timestamps_in_df = res_data_df.index.get_level_values('timestamp')
                        
                        # For 1-min data, we need all bars within the primary candle's interval.
                        # For other secondary data (like 'D'), we just need the latest one up to the current timestamp.
                        if self.primary_resolution == 'D' and res == '1':
                            # When primary is Daily, get all 1-min bars for that entire day by matching the date.
                            current_day = pd.to_datetime(timestamp_ns, unit='s').date()
                            # This is slow, but necessary for this specific cross-resolution analysis.
                            daily_mask = pd.to_datetime(res_data_df.index.get_level_values('timestamp'), unit='s').date == current_day
                            relevant_data = res_data_df[daily_mask]
                        elif res == '1' and self.primary_resolution != 'D':
                            try:
                                # Get all 1-min bars that fall within the start and end of the current primary bar.
                                primary_interval_seconds = pd.to_timedelta(f'{self.primary_resolution}min').total_seconds()
                                start_of_bar_ns = timestamp_ns - primary_interval_seconds
                                relevant_data = res_data_df.loc[(timestamps_in_df >= start_of_bar_ns) & (timestamps_in_df <= timestamp_ns)]
                            except ValueError: # Handle cases where resolution is not a number (e.g., 'D')
                                relevant_data = pd.DataFrame()
                        else:
                            # This is crucial for getting daily data during an intraday loop.
                            relevant_data = res_data_df.loc[timestamps_in_df <= timestamp_ns]

                        if not relevant_data.empty:
                            # Group by symbol and get the last entry for each
                            res_group = relevant_data if res == '1' else relevant_data.groupby('symbol').tail(1)

                # Simplified and corrected data preparation
                if not res_group.empty:
                    if res == self.primary_resolution:
                        # For the primary resolution, build and pass the full history list
                        for row in res_group.itertuples(index=True, name='Pandas'):
                            symbol = row.Index[1]
                            # CRITICAL FIX: The timestamp in the bar history must be the same type as the index (int seconds),
                            # not a datetime object, to ensure consistency for pandas operations within the strategy.
                            bar_data = {'timestamp': timestamp_ns, 'open': row.open, 'high': row.high, 'low': row.low, 'close': row.close, 'volume': row.volume}
                            # CRITICAL FIX: Append the new bar to the history, don't overwrite it.
                            if symbol not in self.bar_history[res]:
                                self.bar_history[res][symbol] = []
                            self.bar_history[res][symbol].append(bar_data)
                        current_market_data_all_resolutions[res] = dict(self.bar_history[res])
                    else:
                        # For secondary resolutions, prepare the data.
                        # For 1-min data, it should be a list of bars.
                        # For other resolutions (like 'D'), it should be a single bar dict.
                        data_for_res = defaultdict(list)
                        for row in res_group.itertuples(index=True, name='Pandas'):
                            symbol = row.Index[1]
                            bar_data = {'open': row.open, 'high': row.high, 'low': row.low, 'close': row.close, 'volume': row.volume}
                            data_for_res[symbol].append(bar_data)
                        
                        # If it's not 1-min data, we only want the single latest bar, not a list.
                        if res != '1':
                            # For other secondary resolutions (like 'D'), the strategy expects a simple dictionary for the single bar, not a list.
                            # This is the definitive fix for the empty debug log issue.
                            data_for_res = {k: v[0] for k, v in data_for_res.items() if v}

                        current_market_data_all_resolutions[res] = data_for_res

            # --- Rule: Time-Windowed Entries & Strategy Execution ---
            if self.start_datetime.time() <= timestamp.time() <= self.end_datetime.time():
                strategy.on_data(timestamp, current_market_data_all_resolutions, is_live_trading=False)

            # --- Rule: Intraday Forced Exits ---
            if backtest_type == 'Intraday' and timestamp.time() >= intraday_exit_time:
                for (symbol, timeframe), position_data in list(portfolio.positions.items()):
                    position_key = (symbol, timeframe)
                    if position_key not in intraday_positions_closed_today:
                        # Correctly get the last close price for the symbol
                        last_bar_for_symbol = self.bar_history[self.primary_resolution].get(symbol, [])
                        close_price = last_bar_for_symbol[-1].get('close') if last_bar_for_symbol else position_data['avg_price']

                        print(f"{timestamp} | INTRADAY EXIT: Force-closing position in {symbol} at {close_price:.2f}.")
                        oms.execute_order({
                            'symbol': symbol, 'timeframe': timeframe, 'action': 'SELL', 'quantity': position_data['quantity'],
                            'price': close_price,
                            'timestamp': timestamp
                        }, is_live_trading=False)
                        intraday_positions_closed_today.add(position_key)

            # Correctly extract the last close price for each symbol from the bar history
            all_prices_at_timestamp = {}
            for res, data_by_symbol in current_market_data_all_resolutions.items():
                for symbol, data in data_by_symbol.items():
                    if isinstance(data, list) and data: # Primary resolution sends a list
                        all_prices_at_timestamp[symbol] = data[-1].get('close')
                    elif isinstance(data, dict): # Secondary resolutions send a single dict
                        all_prices_at_timestamp[symbol] = data.get('close')
            portfolio.log_portfolio_value(timestamp, all_prices_at_timestamp)
        

        # 4. Print the final summary using PerformanceAnalyzer
        print("--- End of Backtest Log ---")
        # Get the last known prices for the final P&L calculation
        last_prices = primary_resolution_data.groupby('symbol')['close'].last().to_dict()
        analyzer = PerformanceAnalyzer(portfolio)
        analyzer.print_performance_report(last_prices, run_id) # This prints to console
        print("-" * 70)
        print(f"Backtest for {strategy_class.__name__} complete.")
        print("-" * 70 + "\n")
        # DEBUG: Print equity curve for inspection
        print("\n[DEBUG] Equity curve sample:")
        for entry in portfolio.equity_curve[:5]:
            print(entry)
        print(f"[DEBUG] Total equity curve points: {len(portfolio.equity_curve)}")
        # Check for missing 'pnl' keys
        missing_pnl = [i for i, entry in enumerate(portfolio.equity_curve) if 'pnl' not in entry]
        if missing_pnl:
            print(f"[DEBUG] WARNING: {len(missing_pnl)} entries missing 'pnl' key. First few: {missing_pnl[:5]}")
        else:
            print("[DEBUG] All entries have 'pnl' key.")
        return portfolio, last_prices, run_id, strategy.get_debug_log() # Return the debug log as well

    def __del__(self):
        """
        Ensures the database connection is closed when the object is destroyed.
        """
        self.con.close()
        # print("Database connection closed.") # Optional: uncomment for debugging