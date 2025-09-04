from .portfolio import Portfolio
from .oms import OrderManager
from ..strategies.base_strategy import BaseStrategy
from fyers_apiv3.FyersWebsocket import data_ws
import json
import os
import datetime
import duckdb
import config # config.py is now in the project root

class LiveTradingEngine:
    """
    The main engine that orchestrates the live paper trading process.
    
    It connects the portfolio, order manager, and strategy, and processes
    incoming live ticks from Fyers WebSocket to simulate trading.
    It also stores live tick data for historical analysis.
    """
    def __init__(self, fyers_model, app_id, strategy: BaseStrategy, initial_cash=100000.0):
        """
        Initializes the LiveTradingEngine.

        Args:
            fyers_model: An authenticated fyersModel instance for REST API calls.
            app_id (str): The Fyers APP_ID for WebSocket connection.
            strategy (BaseStrategy): An instance of a trading strategy.
            initial_cash (float): The starting cash for the portfolio.
        """
        self.fyers = fyers_model
        self.app_id = app_id
        self.portfolio = Portfolio(initial_cash=initial_cash)
        self.oms = OrderManager(self.portfolio, self.fyers) # OMS now needs fyers_model
        self.strategy = strategy
        self.last_known_prices = {} # To store the last price of each symbol
        self.ws = None # WebSocket instance

        # Setup DuckDB connection for storing live ticks into the MARKET database
        self.market_con = duckdb.connect(database=config.MARKET_DB_FILE, read_only=False)
        self.market_con.execute("""
            CREATE TABLE IF NOT EXISTS historical_data (
                timestamp TIMESTAMP,
                symbol VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT
            );
        """)
        print(f"DuckDB connection to '{config.MARKET_DB_FILE}' is ready for live ticks.")

        print("Live Trading Engine initialized.")

    def on_message(self, message):
        """
        Callback function to process incoming WebSocket messages.
        Stores tick data and passes it to the strategy.
        """
        if isinstance(message, dict) and message.get('type') == 'OnQuotes':
            for quote in message.get('quotes', []):
                symbol = quote.get('symbol')
                ltp = quote.get('ltp')
                timestamp_epoch = quote.get('timestamp')
                timestamp = datetime.datetime.fromtimestamp(timestamp_epoch)
                volume = quote.get('volume', 0) # Assuming volume might be available

                if symbol and ltp is not None:
                    self.last_known_prices[symbol] = ltp
                    
                    # Store live tick data in DuckDB
                    try:
                        self.market_con.execute("""
                            INSERT INTO historical_data (timestamp, symbol, open, high, low, close, volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT DO NOTHING;
                        """, [timestamp, symbol, ltp, ltp, ltp, ltp, volume])
                    except Exception as e:
                        print(f"Error storing live tick for {symbol} ({timestamp}): {e}")

                    # Pass the live tick data to the strategy, indicating it's live trading
                    self.strategy.on_data(timestamp, {symbol: {'close': ltp}}, is_live_trading=True) # Using 'close' for consistency with backtest data structure

    def start(self, access_token, symbols_to_subscribe: list):
        """
        Starts the live trading engine by connecting to Fyers WebSocket.

        Args:
            access_token (str): The Fyers access token.
            symbols_to_subscribe (list): List of symbols to subscribe to for live data.
        """
        if self.ws is None:
            self.ws = data_ws.FyersDataSocket(
                access_token=f"{config.APP_ID}:{access_token}",
                log_path=config.LOG_PATH,
                litemode=False, # Set to True for less data
                write_to_file=False
            )
            self.ws.onmessage = self.on_message
            self.ws.onopen = lambda: print("WebSocket connection opened.")
            self.ws.onerror = lambda e: print(f"WebSocket error: {e}")
            self.ws.onclose = lambda: print("WebSocket connection closed.")

            self.ws.connect()
            self.ws.subscribe(symbols=symbols_to_subscribe)
            print(f"Subscribed to symbols: {symbols_to_subscribe}")
        else:
            print("WebSocket already connected.")

    def stop(self):
        """
        Stops the engine, disconnects from WebSocket, and prints a final summary.
        """
        if self.ws:
            self.ws.close()
        print("\n--- Stopping Live Trading Engine ---")
        print("Final Portfolio Performance:")
        self.portfolio.print_final_summary(self.last_known_prices)
        print("-------------------------------------\n")

    def __del__(self):
        """
        Ensures the DuckDB connection is closed when the object is destroyed.
        """
        if self.market_con:
            self.market_con.close()
            print("Market DB connection closed in LiveTradingEngine.")
