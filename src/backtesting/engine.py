# src/backtesting/engine.py

import sqlite3
import pandas as pd
import uuid
import datetime

from src.market_calendar import get_market_close_time
# Use absolute imports from the 'src' root
from src.backtesting.portfolio import BacktestPortfolio
from src.paper_trading.oms import OrderManager
from src.reporting.performance_analyzer import PerformanceAnalyzer
import config # config.py is now in the project root

class BacktestingEngine:
    """
    The core engine for running backtests on historical data.
    """
    def __init__(self, start_datetime: datetime.datetime, end_datetime: datetime.datetime, db_file: str, resolution: str = "D"):
        """_
        Initializes the BacktestingEngine.

        Args:
            start_datetime (datetime.datetime): The start datetime for the backtest.
            end_datetime (datetime.datetime): The end datetime for the backtest.
            db_file (str): The path to the SQLite database file.
            resolution (str): The data resolution to use for the backtest (e.g., "D", "60", "15").
        """
        self.start_datetime = start_datetime
        self.end_datetime = end_datetime
        self.db_file = db_file
        self.resolution = resolution
        # Connect in read-only mode to prevent locking issues with other processes (like data fetchers).
        db_uri = f'file:{self.db_file}?mode=ro'
        self.con = sqlite3.connect(db_uri, uri=True)
        print("Backtesting Engine initialized.")

    def _load_data(self, symbols: list) -> pd.DataFrame:
        """
        Loads historical data from the database for the specified symbols and date range.
        """
        query = f"""
            SELECT timestamp, symbol, close
            FROM historical_data
            WHERE symbol IN ({','.join(['?']*len(symbols))})
            AND resolution = ?
            AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC;
            """
        params = symbols + [self.resolution, self.start_datetime, self.end_datetime]
        df = pd.read_sql_query(query, self.con, params=params, parse_dates=['timestamp'])

        # Set a MultiIndex for efficient grouping and vectorized operations
        if not df.empty:
            df = df.set_index(['timestamp', 'symbol'])
        print(f"Loaded {len(df)} rows of historical data for resolution {self.resolution}.")
        return df

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
        print(f"Resolution: {self.resolution}")
        print(f"Initial Cash: {initial_cash:,.2f}")
        print("-" * 70)

        # 1. Load historical data
        data = self._load_data(symbols)
        if data.empty:
            print("No data found for the given symbols and date range. Aborting backtest.")
            return None, None, None

        # Generate a unique ID for this backtest run to isolate its logs
        run_id = str(uuid.uuid4())
        print(f"Backtest Run ID: {run_id}")

        # 2. Initialize the portfolio and OrderManager
        # Each backtest gets a fresh, isolated portfolio instance.
        portfolio = BacktestPortfolio(initial_cash=initial_cash, run_id=run_id)
        oms = OrderManager(portfolio, run_id=run_id)
        strategy = strategy_class(symbols=symbols, portfolio=portfolio, order_manager=oms, params=params)

        # --- Intraday State Management ---
        market_close_time = get_market_close_time(datetime.date.today()).time()
        intraday_exit_time = (datetime.datetime.combine(datetime.date.today(), market_close_time) - datetime.timedelta(minutes=16)).time()
        intraday_positions_closed_today = set()
        last_processed_date = None

        print("\n--- Backtest Log ---")
        # 3. Event Loop: Iterate through each timestamp in the historical data
        # This simulates the passage of time, candle by candle.
        for timestamp, group in data.groupby(level='timestamp'):
            # `group` is a DataFrame containing all symbol data for the current timestamp
            
            current_date = timestamp.date()
            if last_processed_date and current_date > last_processed_date:
                intraday_positions_closed_today.clear()
            last_processed_date = current_date

            # Format the data for the strategy's on_data method
            current_market_data = {
                row.name[1]: {'close': row['close']} for _, row in group.iterrows()
            }

            # --- Rule: Time-Windowed Entries ---
            if self.start_datetime.time() <= timestamp.time() <= self.end_datetime.time():
                strategy.on_data(timestamp, current_market_data, is_live_trading=False)

            # --- Rule: Intraday Forced Exits ---
            if backtest_type == 'Intraday' and timestamp.time() >= intraday_exit_time:
                for symbol, position_data in list(portfolio.positions.items()):
                    if symbol not in intraday_positions_closed_today:
                        print(f"{timestamp} | INTRADAY EXIT: Force-closing position in {symbol}.")
                        oms.execute_order({
                            'symbol': symbol, 'action': 'SELL', 'quantity': position_data['quantity'],
                            'price': current_market_data.get(symbol, {}).get('close', position_data['avg_price']),
                            'timestamp': timestamp
                        }, is_live_trading=False)
                        intraday_positions_closed_today.add(symbol)

            all_prices_at_timestamp = {symbol: data['close'] for symbol, data in current_market_data.items()}
            portfolio.log_portfolio_value(timestamp, all_prices_at_timestamp)

        # 4. Print the final summary using PerformanceAnalyzer
        print("--- End of Backtest Log ---")
        # Get the last known prices for the final P&L calculation
        last_prices = data.groupby('symbol')['close'].last().to_dict()
        analyzer = PerformanceAnalyzer(portfolio)
        analyzer.print_performance_report(last_prices, run_id)
        print("-" * 70)
        print(f"Backtest for {strategy_class.__name__} complete.")
        print("-" * 70 + "\n")
        return portfolio, last_prices, run_id # Return the portfolio, last prices, and run_id for further analysis

    def __del__(self):
        """
        Ensures the database connection is closed when the object is destroyed.
        """
        self.con.close()
        # print("Database connection closed.") # Optional: uncomment for debugging
