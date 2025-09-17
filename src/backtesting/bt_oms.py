# src/backtesting/bt_oms.py

from src.backtesting.bt_portfolio import BT_Portfolio
from src.symbol_manager import SymbolManager
import sqlite3
import config

class BT_OrderManager:
    """
    Manages simulated order execution for the backtesting engine.
    This is a simplified OMS that only interacts with the BT_Portfolio.
    """
    def __init__(self, portfolio: BT_Portfolio, run_id: str):
        """
        Initializes the BT_OrderManager.

        Args:
            portfolio (BT_Portfolio): The backtest portfolio instance to update.
            run_id (str): A unique identifier for this backtest run.
        """
        self.portfolio = portfolio
        self.run_id = run_id
        self.symbol_manager = SymbolManager()

    def _log_trade(self, signal: dict):
        """Logs a single trade to the database."""
        try:
            with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
                con.execute(
                    """
                    INSERT INTO backtest_trades (run_id, timestamp, symbol, timeframe, action, quantity, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (self.run_id, signal['timestamp'].isoformat(), signal['symbol'], signal['timeframe'],
                     signal['action'], signal['quantity'], signal['price'])
                )
                con.commit()
        except Exception as e:
            print(f"Error logging backtest trade to SQLite: {e}")

    def execute_order(self, signal: dict, is_live_trading: bool = False):
        """
        Executes a simulated trade based on a signal from a strategy.
        The `is_live_trading` flag is ignored here but kept for BaseStrategy compatibility.
        """
        if not all(k in signal for k in ['symbol', 'timeframe', 'action', 'quantity', 'price', 'timestamp']):
            print(f"Invalid signal received: {signal}. Missing required keys.")
            return

        # --- Lot Size Adjustment ---
        lot_size = self.symbol_manager.get_lot_size(signal['symbol'])
        if lot_size > 1:
            final_quantity = (signal['quantity'] // lot_size) * lot_size
        else:
            final_quantity = signal['quantity']

        if final_quantity <= 0:
            return # Silently ignore orders with zero quantity after lot size adjustment

        signal['quantity'] = final_quantity

        # --- Simulated Order Execution ---
        # --- FIX: Ensure the price from the signal is always used ---
        # The strategy is responsible for determining the execution price. For market orders,
        # it's the candle's close. For stop-loss or take-profit exits, it's the
        # specific trigger price. The OMS must honor this price.
        execution_price = signal['price']
        self.portfolio.execute_order(signal['symbol'], signal['timeframe'], signal['action'], signal['quantity'], execution_price, signal['timestamp'])
        self._log_trade(signal)