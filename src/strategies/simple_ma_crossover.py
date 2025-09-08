# src/strategies/simple_ma_crossover.py

from collections import defaultdict
import pandas as pd
from src.paper_trading.oms import OrderManager
from src.paper_trading.portfolio import Portfolio
from src.strategies.base_strategy import BaseStrategy
import numpy as np
from typing import Dict
import datetime
import sys # Added this import

class SMACrossoverStrategy(BaseStrategy):
    """
    A simple moving average (SMA) crossover strategy.
    - Buys when the short-term SMA crosses above the long-term SMA.
    - Sells (to close a position) when the short-term SMA crosses below the long-term SMA.
    """
    def __init__(self, symbols: list[str], portfolio: Portfolio, order_manager: OrderManager, params: dict[str, object], resolutions: list[str] = None):
        """
        Initializes the SMACrossoverStrategy.

        Args:
            symbols (list[str]): A list of symbols to trade.
            portfolio (Portfolio): The portfolio object to interact with.
            order_manager (OrderManager): The OrderManager object to execute trades.
            params (dict[str, object]): A dictionary of parameters, expecting:
                         - 'short_window' (int)
                         - 'long_window' (int)
                         - 'trade_quantity' (int)
        """
        super().__init__(symbols=symbols, portfolio=portfolio, order_manager=order_manager, params=params)
        self.order_manager: OrderManager = order_manager
        def safe_int(val, default):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default
        self.short_window: int = safe_int(self.params.get('short_window', 5), 5)
        self.long_window: int = safe_int(self.params.get('long_window', 20), 20)
        self.trade_quantity: int = safe_int(self.params.get('trade_quantity', 10), 10)
        self.primary_resolution = resolutions[0] if resolutions else "D" # Default primary resolution for this strategy
        self.short_sma: 'defaultdict[str, pd.Series]' = defaultdict(pd.Series)
        self.long_sma: 'defaultdict[str, pd.Series]' = defaultdict(pd.Series)

    @staticmethod
    def get_optimizable_params() -> list[dict]:
        """Defines the parameters that can be optimized for this strategy."""
        return [
            {
                'name': 'short_window',
                'type': 'slider',
                'label': 'Short Window Range',
                'min': 1, 'max': 50, 'default': (5, 15), 'step': 2
            },
            {
                'name': 'long_window',
                'type': 'slider',
                'label': 'Long Window Range',
                'min': 10, 'max': 200, 'default': (20, 50), 'step': 5
            }
        ]

    @staticmethod
    def _generate_param_combinations(opt_params: dict) -> list[dict]:
        short_windows = range(opt_params['short_window'][0], opt_params['short_window'][1] + 1, opt_params.get('short_window_step', 1))
        long_windows = range(opt_params['long_window'][0], opt_params['long_window'][1] + 1, opt_params.get('long_window_step', 1))
        return [{'short_window': sw, 'long_window': lw} for sw in short_windows for lw in long_windows if sw < lw]

    def on_data(self, timestamp: datetime, market_data_all_resolutions: Dict[str, Dict[str, Dict[str, object]]], **kwargs):
        """
        Processes new data (live ticks) and executes trades if a crossover occurs.
        This method is required by the BaseStrategy and used by the LiveTradingEngine.
        """
        
        is_live_trading = kwargs.get('is_live_trading', False)
        
        # Extract data for the primary resolution
        data = market_data_all_resolutions.get(self.primary_resolution, {})

        for symbol in self.symbols:
            if symbol not in data:
                continue

            # The engine now provides the full, managed bar history directly.
            # We convert it to a DataFrame for easy calculation.
            bar_history_list = data[symbol]
            if len(bar_history_list) < self.long_window:
                continue # Not enough data to calculate the long-term SMA

            df = pd.DataFrame(bar_history_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp')

            ltp = df['close'].iloc[-1]

            # --- Calculate SMAs using the full history in the DataFrame ---
            self.short_sma[symbol] = df['close'].rolling(window=self.short_window).mean()
            self.long_sma[symbol] = df['close'].rolling(window=self.long_window).mean()

            # Ensure we have at least two data points to check for a crossover
            if len(self.short_sma[symbol]) < 2 or len(self.long_sma[symbol]) < 2:
                continue # Not enough data for a crossover signal yet

            # Get latest and previous SMA values
            short_sma = self.short_sma[symbol].iloc[-1]
            long_sma = self.long_sma[symbol].iloc[-1]
            prev_short_sma = self.short_sma[symbol].iloc[-2]
            prev_long_sma = self.long_sma[symbol].iloc[-2]

            if not np.isnan(short_sma) and not np.isnan(long_sma) and \
               not np.isnan(prev_short_sma) and not np.isnan(prev_long_sma):
                # --- Rule: Prevent Position Pyramiding ---
                # Check if a position already exists for this symbol before entering a new one.
                position = self.portfolio.get_position(symbol)

                # Bullish Crossover
                if short_sma > long_sma and prev_short_sma <= prev_long_sma and not position:
                    self.buy(symbol, self.trade_quantity, ltp, timestamp, is_live_trading)

                # Bearish Crossover
                elif short_sma < long_sma and prev_short_sma >= prev_long_sma and position and position['quantity'] > 0:
                    self.sell(symbol, abs(position['quantity']), ltp, timestamp, is_live_trading)