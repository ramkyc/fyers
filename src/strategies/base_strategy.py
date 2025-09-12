# src/strategies/base_strategy.py

from abc import ABC, abstractmethod
# Correct the import path to be relative to the src directory
from paper_trading.pt_oms import PT_OrderManager
import datetime
from typing import Dict
import sys

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """

    def __init__(self, symbols: list[str], portfolio: 'Portfolio' = None, order_manager: PT_OrderManager = None, params: dict[str, object] = None, resolutions: list[str] = None):
        """
        Initializes the strategy.

        Args:
            symbols (list[str]): A list of symbols the strategy will trade.
            portfolio (Portfolio): The portfolio object to interact with.
            order_manager (OrderManager, optional): The order manager object to execute trades.
            params (dict[str, object], optional): A dictionary of strategy-specific parameters.
            resolutions (list[str], optional): The data resolutions used, with the first being primary.
        """
        self.symbols: list[str] = symbols
        self.portfolio = portfolio
        self.order_manager = order_manager # This will be set by the engine
        self.params: dict[str, object] = params or {}
        self.primary_resolution = resolutions[0] if resolutions else "1"

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

    def get_required_resolutions(self) -> list[str]:
        """
        Returns a list of data resolutions required by the strategy for its warm-up.
        The first resolution in the list is assumed to be the primary one.
        Subclasses should override this to specify their data needs.
        """
        # Default to 1-minute data if not specified.
        return ["1"]

    @abstractmethod
    def on_data(self, timestamp: datetime, market_data_all_resolutions: Dict[str, Dict[str, Dict[str, object]]], **kwargs):
        """
        This method is called for each new data point (live tick or historical bar).

        Args:
            timestamp (datetime): The timestamp of the current data point.
            market_data_all_resolutions (dict): A dictionary where keys are resolutions (e.g., "D", "60", "1")
                                                and values are dictionaries of market data for that resolution.
                                                Each market data dictionary has symbols as keys and OHLCV data as values.
                                                Example: {"D": {'NSE:SBIN-EQ': {'open': 100, 'high': 105, ...}}}.
            **kwargs: Additional keyword arguments for specific implementations (e.g., is_live_trading).
        """
        
        pass

    def buy(self, symbol: str, timeframe: str, quantity: int, price: float, timestamp: datetime, is_live_trading: bool = False):
        """Places a buy order."""
        signal = {
            'symbol': symbol,
            'timeframe': timeframe,
            'action': 'BUY',
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp
        }
        self.order_manager.execute_order(signal, is_live_trading)

    def sell(self, symbol: str, timeframe: str, quantity: int, price: float, timestamp: datetime, is_live_trading: bool = False):
        """Places a sell order."""
        signal = {
            'symbol': symbol,
            'timeframe': timeframe,
            'action': 'SELL',
            'quantity': quantity,
            'price': price,
            'timestamp': timestamp
        }
        self.order_manager.execute_order(signal, is_live_trading)
