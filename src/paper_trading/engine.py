from src.paper_trading.portfolio import Portfolio
from src.paper_trading.oms import OrderManager
from src.strategies.base_strategy import BaseStrategy
from fyers_apiv3.FyersWebsocket import data_ws
import json
import os
import datetime
import pandas as pd
import sqlite3
import config # config.py is now in the project root

class LiveTradingEngine(data_ws.FyersDataSocket):
    """
    The main engine that orchestrates the live paper trading process.
    
    It connects the portfolio, order manager, and strategy, and processes
    incoming live ticks from Fyers WebSocket to simulate trading.
    It also stores live tick data for historical analysis.
    """
    def __init__(self, fyers_model, app_id, access_token: str, strategy: BaseStrategy, initial_cash=100000.0):
        """
        Initializes the LiveTradingEngine.

        Args:
            fyers_model: An authenticated fyersModel instance for REST API calls.
            app_id (str): The Fyers APP_ID for WebSocket connection.
            access_token (str): The raw Fyers access token.
            strategy (BaseStrategy): An instance of a trading strategy.
            initial_cash (float): The starting cash for the portfolio.
        """
        formatted_token = f"{app_id}:{access_token}"
        
        # Initialize the parent FyersDataSocket, passing our custom methods
        # directly as callbacks. This is the most reliable way to ensure
        # our handlers are used by the library's background thread.
        super().__init__(
            access_token=formatted_token,
            log_path=config.LOG_PATH,
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=self.on_connect,
            on_close=self.on_close,
            on_error=self.on_error,
            on_message=self.on_message
        )

        self.fyers = fyers_model
        self.app_id = app_id
        self.run_id = f"live_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.portfolio = Portfolio(initial_cash=initial_cash, run_id=self.run_id)
        self.oms = OrderManager(self.portfolio, run_id=self.run_id, fyers=self.fyers)

        # --- Critical Linkage ---
        # The strategy needs a reference to the portfolio and OMS created by the engine.
        self.strategy = strategy
        self.strategy.portfolio = self.portfolio
        self.strategy.order_manager = self.oms
        self.last_known_prices = {} # To store the last price of each symbol
        self.tick_counter = 0 # Counter for batch committing
        self.incomplete_bars = {} # For resampling ticks into bars. Key: symbol, Value: OHLC dict
        self.bar_history = {} # For maintaining a rolling history of completed bars for the strategy
        self.symbols_to_subscribe = []

        print("Live Trading Engine initialized.")

    def on_message(self, message):
        """
        Callback function to process incoming WebSocket messages.
        Stores tick data and passes it to the strategy.
        """
        quotes_to_process = []

        # --- Robust Parsing Logic ---
        # Case 1: The message is a dictionary containing a list of quotes under the 'd' key (e.g., 'OnQuotes').
        if isinstance(message, dict) and 'd' in message and isinstance(message['d'], list):
            for item in message['d']:
                if 'v' in item: # The actual quote data is often nested inside a 'v' key
                    quotes_to_process.append(item['v'])

        # Case 2: The message is a simple list of quotes.
        elif isinstance(message, list):
            quotes_to_process.extend(message)

        # Case 3: The message is a single quote dictionary (e.g., 'sf' type).
        elif isinstance(message, dict) and 'symbol' in message:
            quotes_to_process.append(message)

        if quotes_to_process:
            # Process all collected quotes
            for quote in quotes_to_process:
                symbol = quote.get('symbol')
                ltp = quote.get('ltp')
                # The timestamp field name is different in 'sf' vs 'OnQuotes'. We need to check all possibilities.
                timestamp_epoch = quote.get('timestamp') or quote.get('t') or quote.get('last_traded_time')
                volume = quote.get('vol_traded_today', 0)

                if symbol and ltp is not None and timestamp_epoch:
                    timestamp = datetime.datetime.fromtimestamp(timestamp_epoch)
                    self.last_known_prices[symbol] = ltp
                    
                    # Store live tick data in SQLite
                    # NOTE: Connection must be created and used in the same thread.
                    try:
                        with sqlite3.connect(database=config.LIVE_MARKET_DB_FILE) as con:
                            con.execute(
                                "INSERT OR IGNORE INTO live_ticks (timestamp, symbol, ltp, volume) VALUES (?, ?, ?, ?)",
                                (timestamp, symbol, ltp, volume)
                            )
                            self.tick_counter += 1
                            # Commit is handled by the 'with' statement on exit.
                            # We can still print a message for feedback.
                            if self.tick_counter % 100 == 0:
                                print(f"[{datetime.datetime.now()}] Processed 100 ticks.")
                    except Exception as e:
                        print(f"Error storing live tick for {symbol} ({timestamp}) into live_ticks: {e}")

                    # --- Resample Tick to 1-Minute Bar and Execute Strategy ---
                    try:
                        self._resample_and_execute(timestamp, symbol, ltp)
                    except Exception as e:
                        print(f"Error during strategy execution/resampling for {symbol}: {e}")

        else: # This 'else' correctly corresponds to the 'if quotes_to_process:'
            print(f"[{datetime.datetime.now()}] Received non-quote message: {message}")

    def _resample_and_execute(self, current_tick_timestamp: datetime.datetime, symbol: str, price: float):
        """
        Resamples ticks into 1-minute bars. When a bar is complete, it triggers the strategy.
        This method is called for every tick.
        """
        # --- Step 1: Process any completed bars for ALL symbols ---
        # We check all symbols in case one of them has stopped ticking.
        # Iterate over a copy of keys to allow deletion during iteration.
        for s in list(self.incomplete_bars.keys()):
            bar = self.incomplete_bars[s]
            bar_end_time = bar['timestamp'] + datetime.timedelta(minutes=1)

            if current_tick_timestamp >= bar_end_time:
                completed_bar = self.incomplete_bars.pop(s) # Remove from incomplete list
                
                print(f"[{datetime.datetime.now()}] Completed 1m bar for {s}: C={completed_bar['close']}")
                
                # --- Maintain Bar History ---
                if s not in self.bar_history:
                    self.bar_history[s] = []
                self.bar_history[s].append(completed_bar)
                
                # Keep the history to a reasonable length (e.g., long_window + buffer)
                # This prevents memory from growing indefinitely.
                max_history_len = self.strategy.params.get('long_window', 21) + 50
                if len(self.bar_history[s]) > max_history_len:
                    self.bar_history[s].pop(0)

                # Prepare data for the strategy, passing the full available history
                market_data_for_strategy = {'1': {s: self.bar_history[s]}}
                
                # Execute strategy with the completed bar
                try:
                    self.strategy.on_data(completed_bar['timestamp'], market_data_for_strategy, is_live_trading=True)
                except Exception as e:
                    print(f"Error executing strategy.on_data for {s}: {e}")

        # --- Step 2: Update or create the bar for the CURRENT tick's symbol ---
        bar_timestamp = current_tick_timestamp.replace(second=0, microsecond=0)
        if symbol not in self.incomplete_bars:
            # This is the first tick for a new bar
            self.incomplete_bars[symbol] = {
                'timestamp': bar_timestamp,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 0 # Tick volume not available in all messages
            }
        else:
            # Update the existing incomplete bar
            current_bar = self.incomplete_bars[symbol]
            current_bar['high'] = max(current_bar['high'], price)
            current_bar['low'] = min(current_bar['low'], price)
            current_bar['close'] = price

    def on_connect(self):
        """
        Callback function that is triggered when the WebSocket connection is established.
        This is the correct place to subscribe to symbols.
        """
        print(f"[{datetime.datetime.now()}] WebSocket connection established. Subscribing to symbols...")
        self.subscribe(symbols=self.symbols_to_subscribe)

    def on_close(self):
        print(f"[{datetime.datetime.now()}] WebSocket connection closed.")

    def start(self, symbols_to_subscribe: list):
        """
        Starts the live trading engine by connecting to Fyers WebSocket.

        Args:
            symbols_to_subscribe (list): List of symbols to subscribe to for live data.
        """
        self.symbols_to_subscribe = symbols_to_subscribe
        self._warm_up_history()
        
        # Initiate the connection. The parent class will handle the background thread.
        self.connect()

    def _warm_up_history(self):
        """
        Pre-loads the most recent historical bars from the database to provide
        immediate context to the strategy on startup.
        """
        print(f"[{datetime.datetime.now()}] Warming up bar history from pre-populated live strategy table...")

        try:
            # Connect to the LIVE database which now contains the prepared data
            with sqlite3.connect(f'file:{config.LIVE_MARKET_DB_FILE}?mode=ro', uri=True) as con:
                for symbol in self.symbols_to_subscribe:
                    query = "SELECT * FROM live_strategy_data WHERE symbol = ? ORDER BY timestamp ASC;"
                    df = pd.read_sql_query(query, con, params=(symbol,))
                    
                    if not df.empty:
                        self.bar_history[symbol] = df.to_dict('records')
                        print(f"  - Warmed up {len(self.bar_history[symbol])} bars for {symbol}.")
        except Exception as e:
            print(f"Warning: Could not warm up bar history from database. The engine will start 'cold'. Error: {e}")

    def stop(self):
        """
        Stops the engine, disconnects from WebSocket, and prints a final summary.
        """
        # The unsubscribe method requires the list of symbols to stop listening to.
        self.unsubscribe(symbols=self.symbols_to_subscribe)
        
        # --- Process any remaining incomplete bars on shutdown ---
        print(f"[{datetime.datetime.now()}] Processing any remaining incomplete bars before shutdown...")
        for s, bar in self.incomplete_bars.items():
            print(f"[{datetime.datetime.now()}] Force-closing 1m bar for {s}: C={bar['close']}")
            market_data_for_strategy = {'1': {s: bar}}
            try:
                # Use the bar's start time for the event
                self.strategy.on_data(bar['timestamp'], market_data_for_strategy, is_live_trading=True)
            except Exception as e:
                print(f"Error executing strategy on final bar for {s}: {e}")
        self.incomplete_bars.clear()

        # --- Final Commit ---
        # No final commit needed as each message is committed automatically.
        print(f"[{datetime.datetime.now()}] Total ticks processed this session: {self.tick_counter}.")
        print("\n--- Stopping Live Trading Engine ---")
        print("Final Portfolio Performance:")
        self.portfolio.print_final_summary(self.last_known_prices)
        print("-------------------------------------\n")

    def on_error(self, message):
        print(f"[{datetime.datetime.now()}] WebSocket Error: {message}")
