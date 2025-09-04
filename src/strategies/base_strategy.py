# src/strategies/base_strategy.py

from abc import ABC, abstractmethod
import datetime

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """

    def __init__(self, symbols: list[str], portfolio: 'Portfolio', order_manager: 'OrderManager' = None, params: dict[str, object] = None):
        """
        Initializes the strategy.

        Args:
            symbols (list[str]): A list of symbols the strategy will trade.
            portfolio (Portfolio): The portfolio object to interact with.
            order_manager (OrderManager, optional): The order manager object to execute trades.
            params (dict[str, object], optional): A dictionary of strategy-specific parameters.
        """
        self.symbols: list[str] = symbols
        self.portfolio = portfolio
        self.order_manager = order_manager
        self.params: dict[str, object] = params or {}

    @staticmethod
    def get_optimizable_params() -> list[dict]:
        """
        Returns a list of parameters that can be optimized, along with their
        default ranges and types for the UI.

        Returns:
            list[dict]: A list of parameter definition dictionaries.
                        Example: [{'name': 'short_window', 'type': 'slider', 'min': 1, 'max': 50, 'default': (5, 15), 'step': 1}]
        """
        # Base strategy has no optimizable parameters.
        # Subclasses should override this.
        return []

    @abstractmethod
    def on_data(self, timestamp: datetime, data: dict[str, dict[str, object]], **kwargs):
        """
        This method is called for each new data point (live tick or historical bar).

        Args:
            timestamp (datetime): The timestamp of the current data point.
            data (dict[str, dict[str, object]]): A dictionary where keys are symbols and values are the data
                         (e.g., {'NSE:SBIN-EQ': {'close': 350.5, ...}}).
            **kwargs: Additional keyword arguments for specific implementations (e.g., is_live_trading).
        """
        pass

    def buy(self, symbol: str, quantity: int, price: float, timestamp: datetime, is_live_trading: bool = False):
        """Places a buy order."""
        signal = {
            'symbol': symbol,
            'action': 'BUY',
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp
        }
        self.order_manager.execute_order(signal, is_live_trading)

    def sell(self, symbol: str, quantity: int, price: float, timestamp: datetime, is_live_trading: bool = False):
        """Places a sell order."""
        signal = {
            'symbol': symbol,
            'action': 'SELL',
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp
        }
        self.order_manager.execute_order(signal, is_live_trading)
