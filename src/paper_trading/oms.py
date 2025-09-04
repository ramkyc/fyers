# src/paper_trading/oms.py

from .portfolio import Portfolio
from fyers_apiv3 import fyersModel
import datetime
import sqlite3
import os
import config # config.py is now in the project root

class OrderManager:
    """
    Manages order execution, either simulated (for backtesting) or real (for live trading).
    It receives signals from strategies and translates them into trades, updating the portfolio.
    """
    def __init__(self, portfolio: Portfolio, fyers: fyersModel.FyersModel = None):
        """
        Initializes the OrderManager.

        Args:
            portfolio (Portfolio): The portfolio instance to update.
            fyers (fyersModel.FyersModel, optional): An authenticated fyersModel instance for live order placement.
        """
        self.portfolio = portfolio
        self.fyers = fyers
        self._init_trade_log()

    def _init_trade_log(self):
        """Initializes the paper_trades table in the database."""
        with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    timestamp TIMESTAMP,
                    symbol VARCHAR,
                    action VARCHAR,
                    quantity BIGINT,
                    price DOUBLE,
                    is_live BOOLEAN
                );
            """)

    def _log_trade(self, timestamp, symbol, action, quantity, price, is_live):
        """Logs a single trade to the database if logging is enabled."""
        try:
            with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
                con.execute(
                    """
                    INSERT INTO paper_trades (timestamp, symbol, action, quantity, price, is_live)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (timestamp, symbol, action, quantity, price, is_live)
                )
                con.commit()
        except Exception as e:
            print(f"Error logging trade to SQLite: {e}")

    def get_position(self, symbol: str):
        """
        Retrieves the current position for a given symbol from the underlying portfolio.
        """
        return self.portfolio.get_position(symbol)

    def execute_order(self, signal, is_live_trading: bool = False):
        """
        Executes a trade based on a signal from a strategy.

        Args:
            signal (dict): A dictionary containing the trade details.
                           Example: {'symbol': 'RELIANCE-EQ', 'action': 'BUY',
                                     'quantity': 10, 'price': 2800.00, 'timestamp': datetime_obj}
            is_live_trading (bool): If True, attempts to place a real order via Fyers API.
        """
        if not all(k in signal for k in ['symbol', 'action', 'quantity', 'price', 'timestamp']):
            print(f"Invalid signal received: {signal}. Missing required keys.")
            return

        symbol = signal['symbol']
        action = signal['action'].upper()
        quantity = signal['quantity']
        price = signal['price'] # This is the price at which the signal was generated
        timestamp = signal['timestamp']

        if is_live_trading and self.fyers:
            # --- Live Order Placement --- #
            print(f"{timestamp} | Attempting to place LIVE {action} order for {quantity} {symbol}...")
            side = 1 if action == 'BUY' else -1
            order_type = 2 # Market Order
            # Assuming CNC for investment-style strategies. A more complex system
            # would track position types (e.g., INTRADAY vs CNC).
            product_type = "CNC"
            order_data = {
                "symbol": symbol,
                "qty": quantity,
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
                    # For simplicity, we'll use the signal price as execution price for now
                    # A robust system would poll the order book for fill price and quantity.
                    print(f"{timestamp} | LIVE Order for {action} {quantity} {symbol} placed successfully.")
                    self.portfolio.execute_order(symbol, action, quantity, price, timestamp)
                    self._log_trade(timestamp, symbol, action, quantity, price, is_live=True)
                else:
                    print(f"{timestamp} | LIVE Order failed for {symbol}: {response.get('message', 'Unknown error')}")

            except Exception as e:
                print(f"{timestamp} | Error placing LIVE order for {symbol}: {e}")

        else:
            # --- Simulated Order Execution (for backtesting) ---
            print(f"{timestamp} | SIMULATED Order: {action} {quantity} {symbol} @ {price:.2f}")
            self.portfolio.execute_order(symbol, action, quantity, price, timestamp)
            self._log_trade(timestamp, symbol, action, quantity, price, is_live=False)
