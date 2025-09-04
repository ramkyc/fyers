# src/backtesting/engine.py

import sqlite3
import pandas as pd
import os
import sys

from ..paper_trading.portfolio import Portfolio
from ..paper_trading.oms import OrderManager # Import OrderManager
from ..reporting.performance_analyzer import PerformanceAnalyzer
import config # config.py is now in the project root

class BacktestingEngine:
    """
    The core engine for running backtests on historical data.
    """
    def __init__(self, start_date: str, end_date: str, db_file: str, resolution: str = "D"):
        """_
        Initializes the BacktestingEngine.

        Args:
            start_date (str): The start date for the backtest (YYYY-MM-DD).
            end_date (str): The end date for the backtest (YYYY-MM-DD).
            db_file (str): The path to the DuckDB database file.
            resolution (str): The data resolution to use for the backtest (e.g., "D", "60", "15").
        """
        self.start_date = start_date
        self.end_date = end_date
        self.db_file = db_file
        self.resolution = resolution
        self.con = sqlite3.connect(database=self.db_file) #, read_only=True) # SQLite doesn't have a direct read_only parameter in connect
        print("Backtesting Engine initialized.")

    def _load_data(self, symbols: list) -> pd.DataFrame: # Changed return type hint
        """
        Loads historical data from the database and pivots it for easy access.
        """
        symbols_tuple = tuple(symbols)
        query = f"""
            SELECT timestamp, symbol, close
            FROM historical_data
            WHERE symbol IN {symbols_tuple}
            AND resolution = '{self.resolution}'
            AND timestamp BETWEEN '{self.start_date}' AND '{self.end_date}'
            ORDER BY timestamp ASC;
            """
        df = pd.read_sql_query(query, self.con, parse_dates=['timestamp'])

        # Set a MultiIndex for efficient grouping and vectorized operations
        df = df.set_index(['timestamp', 'symbol'])
        print(f"Loaded {len(df)} rows of historical data for resolution {self.resolution}.")
        return df

    def run(self, strategy_class, symbols: list, params: dict, initial_cash=100000.0):
        """
        Runs a backtest for a given strategy.

        Args:
            strategy_class: The class of the strategy to test (e.g., SMACrossoverStrategy).
            symbols (list): The list of symbols to include in the backtest.
            params (dict): The parameters for the strategy.
            initial_cash (float): The starting cash for the portfolio.
        """
        print(f"\n---" + "-" * 20 + f" Starting Backtest: {strategy_class.__name__} " + "-" * 20 + "---")
        print(f"Symbols: {symbols}")
        print(f"Parameters: {params}")
        print(f"Date Range: {self.start_date} to {self.end_date}")
        print(f"Resolution: {self.resolution}")
        print(f"Initial Cash: {initial_cash:,.2f}")
        print("-" * 70)

        # 1. Load historical data
        data = self._load_data(symbols)
        if data.empty:
            print("No data found for the given symbols and date range. Aborting backtest.")
            return None, None

        # 2. Initialize the portfolio and OrderManager
        portfolio = Portfolio(initial_cash=initial_cash, enable_logging=False)
        # The OMS is used to execute trades based on the generated signals.
        # It updates the portfolio state for each simulated trade.
        oms = OrderManager(portfolio)

        # 3. Initialize the strategy and generate all signals at once
        strategy = strategy_class(symbols=symbols, portfolio=portfolio, order_manager=oms, params=params)
        signals = strategy.generate_signals(data)

        # 4. Filter for actual trade signals to iterate over a much smaller dataset
        trades = signals[signals['positions'].isin([1.0, -1.0, 2.0, -2.0])].copy()
        trades['price'] = data.loc[trades.index]['close'] # Get execution price

        print("\n--- Backtest Log ---")
        # 5. Iterate through the trades and update the portfolio
        for index, trade in trades.iterrows():
            timestamp, symbol = index
            price = trade['price']
            
            if trade['positions'] > 0: # Buy signal
                oms.execute_order({
                    'symbol': symbol,
                    'action': 'BUY',
                    'quantity': strategy.trade_quantity,
                    'price': price,
                    'timestamp': timestamp
                }, is_live_trading=False)
            elif trade['positions'] < 0: # Sell signal
                current_position = portfolio.get_position(symbol)
                if current_position:
                    oms.execute_order({
                        'symbol': symbol,
                        'action': 'SELL',
                        'quantity': min(strategy.trade_quantity, current_position['quantity']), # Sell the trade quantity or what's left
                        'price': price,
                        'timestamp': timestamp
                    }, is_live_trading=False)

            # Log portfolio value on every trade for the equity curve
            # Get all current prices for that timestamp for an accurate snapshot
            all_prices_at_timestamp = data.loc[timestamp]['close'].to_dict()
            portfolio.log_portfolio_value(timestamp, all_prices_at_timestamp)

        # 6. Print the final summary using PerformanceAnalyzer
        print("--- End of Backtest Log ---")
        # Get the last known prices for the final P&L calculation
        last_prices = data.groupby('symbol')['close'].last().to_dict()
        analyzer = PerformanceAnalyzer(portfolio)
        analyzer.print_performance_report(last_prices)
        print("-" * 70)
        print(f"Backtest for {strategy_class.__name__} complete.")
        print("-" * 70 + "\n")
        return portfolio, last_prices # Return the portfolio and last prices for further analysis

    def __del__(self):
        """
        Ensures the database connection is closed when the object is destroyed.
        """
        self.con.close()
        # print("Database connection closed.") # Optional: uncomment for debugging
