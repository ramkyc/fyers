# src/strategies/simple_ma_crossover.py

from collections import defaultdict
import pandas as pd
from src.paper_trading.pt_oms import PT_OrderManager
import pandas_ta as ta
from src.paper_trading.pt_portfolio import PT_Portfolio
from .base_strategy import BaseStrategy
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
    def __init__(self, symbols: list[str], portfolio: 'PT_Portfolio' = None, order_manager: 'PT_OrderManager' = None, params: dict[str, object] = None, resolutions: list[str] = None):
        """
        Initializes the SMACrossoverStrategy.

        Args:
            symbols (list[str]): A list of symbols to trade.
            portfolio (PT_Portfolio): The portfolio object to interact with.
            order_manager (PT_OrderManager): The OrderManager object to execute trades.
            params (dict[str, object]): A dictionary of parameters, expecting:
                         - 'short_window' (int)
                         - 'long_window' (int)
                         - 'trade_quantity' (int)
        """
        super().__init__(symbols=symbols, portfolio=portfolio, order_manager=order_manager, params=params, resolutions=resolutions)
        self.order_manager: PT_OrderManager = order_manager
        def safe_int(val, default):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default
        self.short_window: int = safe_int(self.params.get('short_window', 5), 5)
        self.long_window: int = safe_int(self.params.get('long_window', 20), 20)
        self.trade_value: float = float(self.params.get('trade_value', 25000.0))
        # For live trading, the engine provides 1-minute bars. For backtesting, it uses the provided resolutions.
        # If resolutions is None, it implies a live trading context.
        self.primary_resolution = resolutions[0] if resolutions else "1"

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

    def get_required_resolutions(self) -> list[str]:
        """
        This strategy operates on its primary resolution.
        """
        return [self.primary_resolution]

    def on_data(self, timestamp: datetime, market_data_all_resolutions: Dict[str, Dict[str, Dict[str, object]]], **kwargs):
        is_live_trading = kwargs.get('is_live_trading', False)
        data = market_data_all_resolutions.get(self.primary_resolution, {})

        for symbol in self.symbols:
            if symbol not in data:
                continue
            
            bar_history_list = data[symbol]
            if len(bar_history_list) < self.long_window:
                continue # Not enough data to calculate the long-term SMA

            df = pd.DataFrame(bar_history_list)
            # The engine provides timestamps as integers (seconds). We must specify the unit.
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df = df.set_index('timestamp')

            ltp = df['close'].iloc[-1]

            # --- Indicator Calculations using pandas-ta for efficiency ---
            df.ta.sma(length=self.short_window, append=True)
            df.ta.sma(length=self.long_window, append=True)

            # Get latest and previous SMA values
            latest_indicators = df.iloc[-1]
            previous_indicators = df.iloc[-2]

            short_sma = latest_indicators[f'SMA_{self.short_window}']
            long_sma = latest_indicators[f'SMA_{self.long_window}']
            prev_short_sma = previous_indicators[f'SMA_{self.short_window}']
            prev_long_sma = previous_indicators[f'SMA_{self.long_window}']

            if not np.isnan(short_sma) and not np.isnan(long_sma) and \
               not np.isnan(prev_short_sma) and not np.isnan(prev_long_sma):
                position = self.portfolio.get_position(symbol, self.primary_resolution)

                # --- Decision Logic ---
                is_bullish_crossover = short_sma > long_sma and prev_short_sma <= prev_long_sma
                is_bearish_crossover = short_sma < long_sma and prev_short_sma >= prev_long_sma
                
                final_decision = "NO TRADE"
                if is_bullish_crossover and not position:
                    final_decision = "BUY"
                elif is_bearish_crossover and position and position['quantity'] > 0:
                    final_decision = "SELL"

                # --- Structured Debug Logging ---
                self._log_debug({
                    "timestamp": timestamp, "symbol": symbol, "ltp": ltp,
                    "short_sma": short_sma, "long_sma": long_sma,
                    "prev_short_sma": prev_short_sma, "prev_long_sma": prev_long_sma,
                    "final_decision": final_decision
                })

                # Bullish Crossover
                if final_decision == "BUY":
                    if ltp > 0:
                        capital_to_deploy = self.portfolio.get_capital_for_position(symbol, self.primary_resolution, self.trade_value)
                        quantity_to_buy = int(capital_to_deploy / ltp)
                        if quantity_to_buy > 0:
                            self.buy(symbol, self.primary_resolution, quantity_to_buy, ltp, timestamp, is_live_trading)

                # Bearish Crossover
                elif final_decision == "SELL":
                    self.sell(symbol, self.primary_resolution, abs(position['quantity']), ltp, timestamp, is_live_trading)