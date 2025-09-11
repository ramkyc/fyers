# src/paper_trading/pt_oms.py

from src.paper_trading.pt_portfolio import PT_Portfolio
from fyers_apiv3.fyersModel import FyersModel
import datetime
from symbol_manager import SymbolManager
import sqlite3
import os
import config # config.py is now in the project root

class PT_OrderManager:
    """
    Manages order execution for live paper trading and (optionally) real trading.
    It receives signals from strategies and translates them into trades, updating the portfolio.
    """
    def __init__(self, portfolio: PT_Portfolio, run_id: str, fyers: FyersModel = None):
        """
        Initializes the PT_OrderManager.

        Args:
            portfolio (PT_Portfolio): The portfolio instance to update.
            run_id (str): A unique identifier for this trading session or backtest run.
            fyers (FyersModel, optional): An authenticated fyersModel instance for live order placement.
        """
        self.portfolio = portfolio
        self.run_id = run_id
        self.fyers = fyers
        self.symbol_manager = SymbolManager() # Initialize the symbol manager
        # The db_setup.py script is now responsible for all table creation.

    def _log_trade(self, run_id, timestamp, symbol, action, quantity, price, is_live, timeframe):
        """Logs a single trade to the database if logging is enabled."""
        try:
            # Ensure the timestamp is a standard Python datetime object for SQLite compatibility
            if hasattr(timestamp, 'to_pydatetime'):
                timestamp = timestamp.to_pydatetime()

            with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
                con.execute(
                    """
                    INSERT INTO paper_trades (run_id, timestamp, symbol, timeframe, action, quantity, price, is_live)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, timestamp.isoformat(), symbol, timeframe, action, quantity, price, is_live)
                )
                con.commit()
        except Exception as e:
            print(f"Error logging trade to SQLite: {e}")

    def get_position(self, symbol: str):
        """
        DEPRECATED. Positions are now managed by timeframe.
        Retrieves the current position for a given symbol from the underlying portfolio, ignoring timeframe.
        """
        raise NotImplementedError("get_position is deprecated. Use portfolio.get_position(symbol, timeframe) directly.")

    def execute_order(self, signal: dict, is_live_trading: bool = False):
        """
        Executes a trade based on a signal from a strategy.

        Args:
            signal (dict): A dictionary containing the trade details.
                           Example: {'symbol': 'RELIANCE-EQ', 'timeframe': '15', ...}.
            is_live_trading (bool): If True, attempts to place a real order via Fyers API.
        """
        if not all(k in signal for k in ['symbol', 'timeframe', 'action', 'quantity', 'price', 'timestamp']):
            print(f"Invalid signal received: {signal}. Missing required keys.")
            return

        symbol = signal['symbol']
        timeframe = signal['timeframe']
        action = signal['action'].upper()
        requested_quantity = signal['quantity']
        price = signal['price'] # This is the price at which the signal was generated
        timestamp = signal['timestamp']

        # --- Strictly Long-Only Check ---
        # This is a master safety rule to prevent any strategy from initiating a short position.
        if action == 'SELL':
            position = self.portfolio.get_position(symbol, timeframe)
            if not position or position['quantity'] <= 0:
                print(f"{timestamp} | REJECTED SELL: No open long position to sell for {symbol} on {timeframe} timeframe.")
                return

        # --- Lot Size Adjustment ---
        lot_size = self.symbol_manager.get_lot_size(symbol)
        if lot_size > 1:
            # Round down to the nearest multiple of the lot size
            final_quantity = (requested_quantity // lot_size) * lot_size
        else:
            final_quantity = requested_quantity

        if final_quantity <= 0:
            print(f"{timestamp} | INFO: Order for {symbol} rejected. Requested quantity {requested_quantity} is less than lot size {lot_size}.")
            return

        # --- Master Safety Check ---
        # Only proceed with live trading if both the engine flag AND the global config flag are True.
        if is_live_trading and self.fyers and config.ENABLE_LIVE_TRADING:
            # --- Live Order Placement --- #
            print(f"{timestamp} | Attempting to place LIVE {action} order for {final_quantity} {symbol}...")
            side = 1 if action == 'BUY' else -1
            order_type = 2 # Market Order
            # Assuming CNC for investment-style strategies. A more complex system
            # would track position types (e.g., INTRADAY vs CNC).
            product_type = "CNC"
            order_data = {
                "symbol": symbol,
                "qty": final_quantity,
                "type": order_type,
                "side": side,
                "productType": product_type,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
            }

            try:
                response = self.fyers.place_order(data=order_data)
                print(f"Fyers Order Response: {response}")

                if response and response.get("code") == 200:
                    # Order placed successfully. Now update portfolio and log the trade.
                    self.portfolio.execute_order(symbol, timeframe, action, final_quantity, price, timestamp)
                    self._log_trade(self.run_id, timestamp, symbol, action, final_quantity, price, True, timeframe)
                else:
                    print(f"{timestamp} | LIVE Order failed for {symbol}: {response.get('message', 'Unknown error')}")

            except Exception as e:
                print(f"{timestamp} | Error placing LIVE order for {symbol}: {e}")

        else: # This is now only for live paper trading (simulation)
            self.portfolio.execute_order(symbol, timeframe, action, final_quantity, price, timestamp)
            self._log_trade(self.run_id, timestamp, symbol, action, final_quantity, price, True, timeframe) # It's a live paper trade