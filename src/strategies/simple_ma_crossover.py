# src/strategies/simple_ma_crossover.py

from collections import defaultdict
import pandas as pd
from src.paper_trading.oms import OrderManager
from src.paper_trading.portfolio import Portfolio
from src.strategies.base_strategy import BaseStrategy
import numpy as np

class SMACrossoverStrategy(BaseStrategy):
    """
    A simple moving average (SMA) crossover strategy.
    - Buys when the short-term SMA crosses above the long-term SMA.
    - Sells (to close a position) when the short-term SMA crosses below the long-term SMA.
    """
    def __init__(self, symbols: list[str], portfolio: Portfolio, order_manager: OrderManager, params: dict[str, object]):
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
        # Attributes for live trading
        self.price_history: 'defaultdict[str, list[float]]' = defaultdict(list)
        self.short_sma: 'defaultdict[str, float|None]' = defaultdict(lambda: None)
        self.long_sma: 'defaultdict[str, float|None]' = defaultdict(lambda: None)

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

    def on_data(self, timestamp, data: dict[str, dict[str, object]], **kwargs):
        """
        Processes new data (live ticks) and executes trades if a crossover occurs.
        This method is required by the BaseStrategy and used by the LiveTradingEngine.
        """
        is_live_trading = kwargs.get('is_live_trading', False)
        for symbol in self.symbols:
            if symbol not in data:
                continue

            ltp = data[symbol].get('close')
            if ltp is None:
                continue

            self.price_history[symbol].append(ltp)
            if len(self.price_history[symbol]) < self.long_window:
                continue

            # Keep history from getting too large
            if len(self.price_history[symbol]) > self.long_window + 5:
                self.price_history[symbol].pop(0)

            prices = pd.Series(self.price_history[symbol])
            short_sma = prices.rolling(window=self.short_window).mean().iloc[-1]
            long_sma = prices.rolling(window=self.long_window).mean().iloc[-1]

            prev_short_sma = self.short_sma[symbol]
            prev_long_sma = self.long_sma[symbol]

            if prev_short_sma is not None and prev_long_sma is not None:
                # --- Rule: Prevent Position Pyramiding ---
                # Check if a position already exists for this symbol before entering a new one.
                position = self.portfolio.get_position(symbol)

                # Bullish Crossover
                if short_sma > long_sma and prev_short_sma <= prev_long_sma and not position:
                    print(f"SIGNAL: Bullish crossover for {symbol}. Placing BUY order.")
                    self.buy(symbol, self.trade_quantity, ltp, timestamp, is_live_trading)

                # Bearish Crossover
                elif short_sma < long_sma and prev_short_sma >= prev_long_sma and position:
                    print(f"SIGNAL: Bearish crossover for {symbol}. Placing SELL order.")
                    self.sell(symbol, abs(position['quantity']), ltp, timestamp, is_live_trading)

            self.short_sma[symbol] = short_sma
            self.long_sma[symbol] = long_sma