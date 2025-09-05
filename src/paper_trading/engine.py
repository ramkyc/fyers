from .portfolio import Portfolio
from .oms import OrderManager
from ..strategies.base_strategy import BaseStrategy
from fyers_apiv3.FyersWebsocket import data_ws
import json
import os
import datetime
import sqlite3
import config # config.py is now in the project root

class FyersSocketManager(data_ws.FyersDataSocket):
    """
    A custom WebSocket manager that inherits from FyersDataSocket.
    This is the correct way to handle WebSocket events, by overriding
    the library's built-in callback methods.
    """
    def __init__(self, access_token, log_path):
        """
        Initializes the custom socket manager.

        Args:
            access_token (str): The formatted Fyers access token.
            log_path (str): The path for storing logs.
        """
        # Call the parent class constructor
        super().__init__(
            access_token=access_token,
            log_path=log_path,
            litemode=False,
            write_to_file=False,
            reconnect=True
        )
        # The engine instance will be attached here after initialization
        self.engine = None

    def on_connect(self):
        """
        This method is called by the Fyers library when the connection is established.
        We override it to call our custom 'on_open' logic.
        """
        if self.engine:
            self.engine.on_open()

    def on_message(self, message):
        """
        This method is called by the Fyers library for every message.
        We override it to call our custom message processing logic.
        """
        if self.engine:
            self.engine.on_message(message)

    def on_error(self, message):
        """
        This method is called by the Fyers library on an error.
        """
        # The engine can handle this if needed, for now just print
        print(f"WebSocket error: {message}")

    def on_close(self, message):
        """
        This method is called by the Fyers library when the connection closes.
        """
        print(f"WebSocket connection closed: {message}")
        if self.engine:
            self.engine.on_close()


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

        # --- Critical Linkage ---
        # The strategy needs a reference to the portfolio and OMS created by the engine.
        self.strategy.portfolio = self.portfolio
        self.strategy.order_manager = self.oms
        self.last_known_prices = {} # To store the last price of each symbol
        self.ws = None # WebSocket instance
        self.tick_counter = 0 # Counter for batch committing
        self.symbols_to_subscribe = []

        # Setup SQLite connection for storing live ticks into the MARKET database
        self.market_con = sqlite3.connect(database=config.LIVE_MARKET_DB_FILE)
        # Use a dedicated table for live ticks with a simple schema
        self.market_con.execute("""
            CREATE TABLE IF NOT EXISTS live_ticks (
                timestamp TIMESTAMP,
                symbol TEXT,
                ltp REAL,
                volume INTEGER,
                UNIQUE(timestamp, symbol)
            );
        """)
        self.market_con.commit()
        print(f"SQLite connection to '{config.LIVE_MARKET_DB_FILE}' (table: live_ticks) is ready.")

        print("Live Trading Engine initialized.")

    def on_message(self, message):
        """
        Callback function to process incoming WebSocket messages.
        Stores tick data and passes it to the strategy.
        """
        # The most common format for symbolData is a list containing a dictionary.
        # We need to handle this first and foremost.
        quotes_to_process = []
        
        # Primary case: Live tick data arrives as a list.
        if isinstance(message, list) and len(message) > 0:
            # The list itself contains the quote dictionaries.
            quotes_to_process.extend(message)
        
        # Secondary case: Sometimes messages are single dictionaries (like 'sf' for symbol feed).
        elif isinstance(message, dict) and message.get('type') == 'sf':
            quotes_to_process.append(message)

        if quotes_to_process:
            # Process all collected quotes
            for quote in quotes_to_process:
                symbol = quote.get('symbol')
                ltp = quote.get('ltp')
                # The timestamp field name is different in 'sf' vs 'OnQuotes'
                timestamp_epoch = quote.get('timestamp') or quote.get('t')
                volume = quote.get('vol_traded_today', 0)

                if symbol and ltp is not None and timestamp_epoch:
                    timestamp = datetime.datetime.fromtimestamp(timestamp_epoch)
                    self.last_known_prices[symbol] = ltp
                    
                    # Store live tick data in SQLite
                    try:
                        self.market_con.execute(
                            "INSERT OR IGNORE INTO live_ticks (timestamp, symbol, ltp, volume) VALUES (?, ?, ?, ?)",
                            (timestamp, symbol, ltp, volume)
                        )
                        self.tick_counter += 1
                        # Commit to the database in batches of 100 to improve performance
                        if self.tick_counter % 100 == 0:
                            self.market_con.commit()
                            print(f"[{datetime.datetime.now()}] Committed 100 ticks to the database.")
                    except Exception as e:
                        print(f"Error storing live tick for {symbol} ({timestamp}) into live_ticks: {e}")

                    # Pass the live tick data to the strategy, isolating any potential errors
                    try:
                        # This call will trigger the OMS to log the trade if one occurs
                        self.strategy.on_data(timestamp, {symbol: {'close': ltp}}, is_live_trading=True)

                        # Log portfolio value after every tick for live monitoring
                        summary = self.portfolio.get_performance_summary(self.last_known_prices)
                        with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
                            con.execute(
                                """
                                INSERT INTO portfolio_log (timestamp, total_portfolio_value, cash, holdings_value, realized_pnl, unrealized_pnl)
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (timestamp, summary['total_portfolio_value'], summary['final_cash'], summary['holdings_value'], summary['realized_pnl'], summary['unrealized_pnl'])
                            )
                            con.commit()

                    except Exception as e:
                        print(f"Error executing strategy.on_data for {symbol}: {e}")
        else: # This 'else' correctly corresponds to the 'if quotes_to_process:'
            print(f"[{datetime.datetime.now()}] Received non-quote message: {message}")

    def on_open(self):
        """
        Callback function that is triggered when the WebSocket connection is established.
        This is the correct place to subscribe to symbols.
        """
        # This is now primarily a confirmation message. Subscriptions are handled in start().
        print(f"[{datetime.datetime.now()}] WebSocket connection established and is open.")

    def on_close(self):
        print(f"[{datetime.datetime.now()}] WebSocket connection closed by server.")

    def start(self, access_token, symbols_to_subscribe: list):
        """
        Starts the live trading engine by connecting to Fyers WebSocket.

        Args:
            access_token (str): The Fyers access token.
            symbols_to_subscribe (list): List of symbols to subscribe to for live data.
        """
        if self.ws is None:
            self.symbols_to_subscribe = symbols_to_subscribe
            # Use our custom FyersSocketManager class that correctly handles callbacks
            self.ws = FyersSocketManager(
                access_token=f"{config.APP_ID}:{access_token}",
                log_path=config.LOG_PATH
            )
            # Link the engine to the socket manager
            self.ws.engine = self
            self.ws.connect()

            # According to documentation, it's best to subscribe after connect() is called.
            # This ensures the commands are sent once the socket is ready.
            print(f"Subscribing to {len(self.symbols_to_subscribe)} symbols...")
            self.ws.subscribe(symbols=self.symbols_to_subscribe)
            self.ws.set_data_type(data_type="symbolData")
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
        Ensures the SQLite connection is closed when the object is destroyed.
        """
        if self.market_con:
            self.market_con.commit() # Commit any pending changes
            self.market_con.close()
            print("Market DB connection closed in LiveTradingEngine.")
