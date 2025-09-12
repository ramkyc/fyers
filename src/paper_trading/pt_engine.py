from paper_trading.pt_portfolio import PT_Portfolio
from paper_trading.pt_oms import PT_OrderManager
from strategies.base_strategy import BaseStrategy
from fyers_apiv3.FyersWebsocket import data_ws
import json
import os
import datetime
import pandas as pd
from collections import defaultdict
import sqlite3
import config # config.py is now in the project root

class PT_Engine(data_ws.FyersDataSocket):
    """
    The main engine that orchestrates the live paper trading process.
    
    It connects the portfolio, order manager, and strategy, and processes
    incoming live ticks from Fyers WebSocket to simulate trading.
    It also stores live tick data for historical analysis. It can manage and execute multiple strategies concurrently on a single portfolio.
    """
    def __init__(self, fyers_model, app_id, access_token: str, strategies: list[BaseStrategy], paper_trade_type: str = 'Intraday', initial_cash=5000000.0):
        """
        Initializes the PT_Engine.

        Args:
            fyers_model: An authenticated fyersModel instance for REST API calls.
            app_id (str): The Fyers APP_ID for WebSocket connection.
            access_token (str): The raw Fyers access token.
            strategies (list[BaseStrategy]): A list of instantiated trading strategies.
            paper_trade_type (str): The type of paper trading ('Intraday' or 'Positional').
            initial_cash (float): The starting cash for the portfolio.
        """
        formatted_token = f"{app_id}:{access_token}"

        self.fyers = fyers_model
        self.app_id = app_id
        self.run_id = f"live_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.paper_trade_type = paper_trade_type
        self.portfolio = PT_Portfolio(initial_cash=initial_cash, run_id=self.run_id)
        self.oms = PT_OrderManager(self.portfolio, run_id=self.run_id, fyers=self.fyers)

        # --- Critical Linkage ---
        # Each strategy needs a reference to the shared portfolio and OMS.
        self.strategies = strategies
        for strategy in self.strategies:
            strategy.portfolio = self.portfolio
            strategy.order_manager = self.oms
        # Create a quick lookup map from timeframe to strategy instance
        self.timeframe_to_strategy = {s.primary_resolution: s for s in self.strategies}

        self.last_known_prices = {} # To store the last price of each symbol
        self.tick_counter = 0 # Counter for batch committing
        # New structure for multi-resolution resampling
        # Key: resolution (str), Value: {symbol: OHLC dict}
        self.incomplete_bars = defaultdict(dict)

        self.bar_history = {} # For maintaining a rolling history of completed bars for the strategy
        self.symbols_to_subscribe = []

        # --- State for Live Crossover Counting ---
        self.live_daily_open = {}
        self.live_crossover_counts = defaultdict(int)
        self.last_tick_price = {}

        # --- Intraday State Management ---
        self.intraday_exit_time = datetime.time(15, 14) # 3:14 PM
        self.intraday_positions_closed_today = set()
        self.last_processed_date = None

        # --- Final Initialization of Parent Class ---
        # This MUST be called last, after all our custom attributes are set up.
        # This ensures that when the parent's background thread starts and calls our
        # callbacks (like on_message), our instance is fully ready.
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
        print("Live Paper Trading Engine initialized.")

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

                    # --- Daily State Reset ---
                    current_date = timestamp.date()
                    if self.last_processed_date != current_date:
                        self.intraday_positions_closed_today.clear()
                        self.last_processed_date = current_date

                    self.last_known_prices[symbol] = ltp
                    
                    # --- Live Crossover Counting Logic ---
                    # 1. Set the daily open on the first tick of the day
                    if symbol not in self.live_daily_open:
                        self.live_daily_open[symbol] = ltp
                        self.last_tick_price[symbol] = ltp

                    # 2. Check for an upward crossover
                    # A crossover happens if the previous price was below the open and the current price is at or above it.
                    if self.last_tick_price.get(symbol, ltp) < self.live_daily_open.get(symbol, ltp) and ltp >= self.live_daily_open.get(symbol, ltp):
                        self.live_crossover_counts[symbol] += 1

                    # 3. Update the last known price for the next tick
                    self.last_tick_price[symbol] = ltp

                    # Store live tick data in SQLite
                    # NOTE: Connection must be created and used in the same thread.
                    try:
                        with sqlite3.connect(database=config.LIVE_MARKET_DB_FILE) as con:
                            con.execute(
                                "INSERT OR IGNORE INTO live_ticks (timestamp, symbol, ltp, volume) VALUES (?, ?, ?, ?)",
                                (timestamp.isoformat(), symbol, ltp, volume)
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

    def _log_live_portfolio_value(self, timestamp):
        """Logs the current portfolio value to the database for live tracking."""
        try:
            summary = self.portfolio.get_performance_summary(self.last_known_prices)
            with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
                cursor = con.cursor()
                # 1. Ensure the table exists with a minimal schema.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS portfolio_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        timestamp DATETIME NOT NULL
                    );
                """)

                # 2. Check for and add missing columns to handle schema evolution.
                cursor.execute("PRAGMA table_info(portfolio_log)")
                columns = [info[1] for info in cursor.fetchall()]
                
                if 'value' not in columns:
                    cursor.execute("ALTER TABLE portfolio_log ADD COLUMN value REAL;")
                if 'cash' not in columns:
                    cursor.execute("ALTER TABLE portfolio_log ADD COLUMN cash REAL;")
                if 'holdings' not in columns:
                    cursor.execute("ALTER TABLE portfolio_log ADD COLUMN holdings REAL;")

                # 3. Insert the data.
                cursor.execute(
                    """
                    INSERT INTO portfolio_log (run_id, timestamp, value, cash, holdings)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.run_id,
                        timestamp.isoformat(),
                        summary['total_portfolio_value'],
                        summary['final_cash'],
                        summary['holdings_value']
                    )
                )
                con.commit() # Explicitly commit the transaction
        except Exception as e:
            print(f"Error logging live portfolio value: {e}")

    def _log_live_positions(self, timestamp):
        """Logs the current open positions to the database for live tracking."""
        try:
            with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
                cursor = con.cursor()
                if not self.portfolio.positions:
                    return

                positions_to_log = []
                for (symbol, timeframe), data in self.portfolio.positions.items():
                    ltp = self.last_known_prices.get(symbol, data['avg_price'])
                    mtm = (ltp - data['avg_price']) * data['quantity']

                    # Get the corresponding strategy to fetch SL/TP details
                    strategy = self.timeframe_to_strategy.get(timeframe)
                    trade_details = strategy.active_trades.get(symbol) if strategy else None

                    positions_to_log.append((
                        self.run_id, timestamp.isoformat(), symbol, timeframe,
                        data['quantity'], data['avg_price'], ltp, mtm,
                        trade_details.get('stop_loss') if trade_details else None,
                        trade_details.get('target1') if trade_details else None,
                        trade_details.get('target2') if trade_details else None,
                        trade_details.get('target3') if trade_details else None,
                    ))
                
                cursor.executemany(
                    "INSERT OR REPLACE INTO live_positions (run_id, timestamp, symbol, timeframe, quantity, avg_price, ltp, mtm, stop_loss, target1, target2, target3) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    positions_to_log
                )
                con.commit()
        except Exception as e:
            print(f"Error logging live positions: {e}")

    def _resample_and_execute(self, current_tick_timestamp: datetime.datetime, symbol: str, price: float):
        """
        Resamples ticks into 1-minute bars. When a bar is complete, it triggers the strategy.
        This method is called for every tick.
        """
        # This method's ONLY responsibility is to create 1-minute bars.
        bar_timestamp = current_tick_timestamp.replace(second=0, microsecond=0)

        # Check if the tick belongs to a new 1-minute bar
        if symbol not in self.incomplete_bars['1'] or bar_timestamp > self.incomplete_bars['1'][symbol]['timestamp']:
            # If a previous incomplete bar exists, it is now complete.
            if symbol in self.incomplete_bars['1']:
                completed_1m_bar = self.incomplete_bars['1'].pop(symbol)
                self._process_completed_bar(completed_1m_bar, '1', symbol)

            # This is the first tick for a new bar
            self.incomplete_bars['1'][symbol] = {
                'timestamp': bar_timestamp,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 0 # Tick volume not available in all messages
            }
        else:
            # Update the existing incomplete bar
            current_bar = self.incomplete_bars['1'][symbol]
            current_bar['high'] = max(current_bar['high'], price)
            current_bar['low'] = min(current_bar['low'], price)
            current_bar['close'] = price

        # --- Persist the state of the incomplete bar for the live chart UI ---
        try:
            with sqlite3.connect(database=config.LIVE_MARKET_DB_FILE) as con:
                con.execute(
                    "INSERT OR REPLACE INTO live_incomplete_bars VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (symbol, self.incomplete_bars['1'][symbol]['timestamp'].isoformat(), self.incomplete_bars['1'][symbol]['open'], 
                     self.incomplete_bars['1'][symbol]['high'], self.incomplete_bars['1'][symbol]['low'], 
                     self.incomplete_bars['1'][symbol]['close'], self.incomplete_bars['1'][symbol]['volume'])
                )
        except Exception as e:
            print(f"Error persisting incomplete bar for {symbol}: {e}")

    def _resample_higher_timeframes(self, completed_1m_bar: dict, symbol: str):
        """
        Takes a completed 1-minute bar and resamples it into higher timeframes.
        """
        resolutions_to_process = ['5', '15', '30', '60']
        bar_timestamp = completed_1m_bar['timestamp']

        for res_str in resolutions_to_process:
            resolution = int(res_str)
            
            # Check if the 1-minute bar completes a higher-timeframe bar
            if (bar_timestamp.minute + 1) % resolution == 0:
                # The higher timeframe bar is now complete. We need to construct it.
                history_key_1m = (symbol, '1')
                if history_key_1m not in self.bar_history or len(self.bar_history[history_key_1m]) < resolution:
                    continue # Not enough 1-min data to build this bar

                # Get the last N 1-minute bars to build the higher timeframe bar
                relevant_1m_bars = self.bar_history[history_key_1m][-resolution:]
                
                # Construct the higher timeframe bar
                higher_tf_bar = {
                    'timestamp': relevant_1m_bars[0]['timestamp'], # Starts at the beginning of the period
                    'open': relevant_1m_bars[0]['open'],
                    'high': max(b['high'] for b in relevant_1m_bars),
                    'low': min(b['low'] for b in relevant_1m_bars),
                    'close': relevant_1m_bars[-1]['close'],
                    'volume': sum(b['volume'] for b in relevant_1m_bars)
                }
                self._process_completed_bar(higher_tf_bar, res_str, symbol)

    def _process_completed_bar(self, completed_bar: dict, resolution: str, symbol: str):
        """
        Handles all logic for a completed bar: persisting, updating history,
        and executing the correct strategy instance.
        """
        # --- Persist Completed Bar for Live Charts (only for 1-min) ---
        if resolution == '1':
            # This is the authoritative source for the live charts UI
            try:
                with sqlite3.connect(database=config.LIVE_MARKET_DB_FILE) as con:
                    con.execute(
                        "INSERT OR REPLACE INTO live_strategy_data (timestamp, symbol, resolution, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (completed_bar['timestamp'].isoformat(), symbol, resolution, completed_bar['open'], completed_bar['high'], completed_bar['low'], completed_bar['close'], completed_bar['volume'])
                    )
            except Exception as e:
                print(f"Error persisting completed 1-min bar for {symbol}: {e}")

        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Completed {resolution}m bar for {symbol}: C={completed_bar['close']}")

        # --- Maintain Bar History for each resolution ---
        history_key = (symbol, resolution)
        if history_key not in self.bar_history:
            self.bar_history[history_key] = []
        self.bar_history[history_key].append(completed_bar)

        # --- Trigger Higher Timeframe Resampling (only from 1-min bars) ---
        if resolution == '1':
            self._resample_higher_timeframes(completed_bar, symbol)

        # --- Find and Execute the Correct Strategy Instance ---
        for strategy in self.strategies:
            if strategy.primary_resolution == resolution:
                # Keep history to a reasonable length
                max_lookback = max(strategy.params.get('long_window', 0), strategy.params.get('ema_slow', 0), 21)
                max_history_len = max_lookback + 150 # Increased buffer
                if len(self.bar_history[history_key]) > max_history_len:
                    self.bar_history[history_key].pop(0)

                # --- Prepare Multi-Timeframe Data Packet ---
                market_data_for_strategy = defaultdict(dict)
                
                # The strategy needs data for ALL its required resolutions.
                for res in strategy.get_required_resolutions():
                    history_key_for_res = (symbol, res)
                    if history_key_for_res in self.bar_history:
                        if res == 'D':
                            # For daily data, provide the single latest bar as a list containing the dict.
                            # This ensures that when the strategy creates a DataFrame, the columns are preserved.
                            market_data_for_strategy[res][symbol] = [self.bar_history[history_key_for_res][-1]]
                        else:
                            # For intraday data, provide the full history
                            market_data_for_strategy[res][symbol] = self.bar_history[history_key_for_res]
                
                try:
                    strategy.on_data(
                        completed_bar['timestamp'], 
                        market_data_for_strategy, 
                        is_live_trading=True, 
                        live_crossover_count=self.live_crossover_counts.get(symbol, 0)
                    )
                except Exception as e:
                    print(f"Error executing strategy {type(strategy).__name__} on {resolution}m bar for {symbol}: {e}")

        # Reset crossover count only after the 1-minute bar is processed
        if resolution == '1' and symbol in self.live_crossover_counts:
            self.live_crossover_counts[symbol] = 0

        # --- Log Portfolio and Positions (only on the 1-minute interval to avoid excessive logging) ---
        if resolution == '1':
            self._log_live_portfolio_value(completed_bar['timestamp'])
            self._log_live_positions(completed_bar['timestamp'])

            # --- Rule: Intraday Forced Exits (checked on every 1-min bar) ---
            if self.paper_trade_type == 'Intraday' and completed_bar['timestamp'].time() >= self.intraday_exit_time:
                for (pos_symbol, pos_timeframe), position_data in list(self.portfolio.positions.items()):
                    position_key = (pos_symbol, pos_timeframe)
                    if position_key not in self.intraday_positions_closed_today:
                        print(f"[{completed_bar['timestamp']}] INTRADAY EXIT: Force-closing position in {pos_symbol} on {pos_timeframe} timeframe.")
                        self.oms.execute_order({'symbol': pos_symbol, 'timeframe': pos_timeframe, 'action': 'SELL', 'quantity': position_data['quantity'], 'price': self.last_known_prices.get(pos_symbol, 0), 'timestamp': completed_bar['timestamp']}, is_live_trading=True)
                        self.intraday_positions_closed_today.add(position_key)

    def on_connect(self):
        """
        Callback function that is triggered when the WebSocket connection is established.
        This is the correct place to subscribe to symbols.
        """
        print(f"[{datetime.datetime.now()}] WebSocket connection established. Subscribing to symbols...")
        self.subscribe(symbols=self.symbols_to_subscribe)

    def on_close(self, *args, **kwargs):
        """
        Callback function for when the connection is closed.
        Accepts variable arguments to be compatible with the library's call signature.
        """
        print(f"[{datetime.datetime.now()}] WebSocket connection closed. Args: {args}, Kwargs: {kwargs}")

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
                # Get all unique symbols and resolutions that were prepared for this session.
                all_prepared_data = pd.read_sql_query("SELECT DISTINCT symbol, resolution FROM live_strategy_data;", con)

                # Iterate through all prepared data, not just the symbols we subscribe to.
                # This ensures we load the daily data for underlying indices.
                for _, row in all_prepared_data.iterrows():
                    symbol, res = row['symbol'], row['resolution']
                    query = "SELECT * FROM live_strategy_data WHERE symbol = ? AND resolution = ? ORDER BY timestamp ASC;"
                    df = pd.read_sql_query(query, con, params=(symbol, res))
                    
                    if not df.empty:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        self.bar_history[(symbol, res)] = df.to_dict('records')
                        print(f"  - Warmed up {len(df)} bars for {symbol} at {res} resolution.")
        except Exception as e:
            print(f"Warning: Could not warm up bar history from database. The engine will start 'cold'. Error: {e}")

    def stop(self):
        """
        Stops the engine, disconnects from WebSocket, and prints a final summary.
        """
        shutdown_timestamp = datetime.datetime.now()
        print(f"[{shutdown_timestamp}] Initiating graceful shutdown...")

        # --- Process any remaining incomplete bars and square off positions BEFORE disconnecting ---
        print(f"[{datetime.datetime.now()}] Processing any remaining incomplete bars before shutdown...")
        for s, bar in self.incomplete_bars.get('1', {}).items():
            print(f"[{datetime.datetime.now()}] Force-closing 1m bar for {s}: C={bar['close']}")
            self._process_completed_bar(bar, '1', s)
        self.incomplete_bars.clear()

        if self.portfolio.positions:
            print("Squaring off all open positions...")
            for (symbol, timeframe), position_data in list(self.portfolio.positions.items()):
                if position_data['quantity'] > 0:
                    last_price = self.last_known_prices.get(symbol, position_data['avg_price'])
                    print(f"  - Closing {position_data['quantity']} of {symbol} ({timeframe}) at last known price {last_price:.2f}")
                    self.oms.execute_order({'symbol': symbol, 'timeframe': timeframe, 'action': 'SELL', 'quantity': position_data['quantity'], 'price': last_price, 'timestamp': shutdown_timestamp}, is_live_trading=False)

        if self.is_connected():
            self.unsubscribe(symbols=self.symbols_to_subscribe)
        
        # --- Non-Blocking WebSocket Closure ---
        # The close_connection() can sometimes block indefinitely.
        # We will attempt to close it but will not wait for it, allowing the main process to exit.
        # The OS will clean up the orphaned background thread.
        try:
            print(f"[{datetime.datetime.now()}] Closing WebSocket connection...")
            self.close_connection()
        except Exception as e:
            print(f"[{datetime.datetime.now()}] Non-critical error during WebSocket closure: {e}")

        # --- Final Commit ---
        # No final commit needed as each message is committed automatically.
        print(f"[{datetime.datetime.now()}] Total ticks processed this session: {self.tick_counter}.")
        print("\n--- Stopping Live Trading Engine ---")
        print("Final Portfolio Performance:")
        self.portfolio.print_final_summary(self.last_known_prices, context="Live Session")
        print("-------------------------------------\n")

    def on_error(self, message):
        print(f"[{datetime.datetime.now()}] WebSocket Error: {message}")