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
        self.trade_value: float = float(self.params.get('trade_value', 25000.0))
        # For live trading, the engine provides 1-minute bars. For backtesting, it uses the provided resolutions.
        # If resolutions is None, it implies a live trading context.
        self.primary_resolution = resolutions[0] if resolutions else "1"
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

    def get_required_resolutions(self) -> list[str]:
        """
        This strategy operates on its primary resolution.
        """
        return [self.primary_resolution]

    def _log_live_decision_data(self, symbol: str, timestamp: datetime.datetime, data: dict):
        """Helper to log the data used for making a live trade decision."""
        def _format_float(value):
            """Safely formats a float or returns 'nan'."""
            if isinstance(value, (int, float)) and not np.isnan(value):
                return f"{value:.2f}"
            return "nan"

        ltp = data.get('ltp', 'N/A')
        short_sma = data.get('short_sma', 'N/A')
        long_sma = data.get('long_sma', 'N/A')
        prev_short_sma = data.get('prev_short_sma', 'N/A')
        prev_long_sma = data.get('prev_long_sma', 'N/A')
        position_exists = data.get('position_exists', 'N/A')
        
        bullish_crossover_check = "N/A"
        if all(isinstance(v, (int, float)) and not np.isnan(v) for v in [short_sma, long_sma, prev_short_sma, prev_long_sma]):
             bullish_crossover_check = (short_sma > long_sma and prev_short_sma <= prev_long_sma)

        print(
            f"[{timestamp}] DEBUG FOR {symbol}:\n"
            f"  - LTP: {_format_float(ltp)}\n"
            f"  - Short SMA (curr/prev): {_format_float(short_sma)} / {_format_float(prev_short_sma)}\n"
            f"  - Long SMA (curr/prev): {long_sma:.2f} / {_format_float(prev_long_sma)}\n"
            f"  - Position Exists: {position_exists}\n"
            f"  - Bullish Crossover Condition Met: {bullish_crossover_check}\n"
            f"  --------------------------------------------------"
        )
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
            
            bar_history_list = data[symbol]

            # --- Robustness Check for Shutdown ---
            # On shutdown, we might receive a list with only one bar. This check prevents errors.
            if len(bar_history_list) < 2:
                continue

            # --- LOGGING BLOCK (Moved Up) ---
            # We log here to see the state on every bar, even before we have enough data for indicators.
            if is_live_trading:
                df_temp = pd.DataFrame(bar_history_list)
                
                # Initialize all values to NaN
                short_sma_val, prev_short_sma_val = np.nan, np.nan
                long_sma_val, prev_long_sma_val = np.nan, np.nan
                ltp = df_temp['close'].iloc[-1] if not df_temp.empty else np.nan

                # Calculate SMAs only if enough data exists
                if len(df_temp) >= self.short_window:
                    short_sma_series = df_temp['close'].rolling(window=self.short_window).mean()
                    short_sma_val = short_sma_series.iloc[-1]
                    if len(df_temp) >= self.short_window + 1:
                        prev_short_sma_val = short_sma_series.iloc[-2]

                if len(df_temp) >= self.long_window:
                    long_sma_series = df_temp['close'].rolling(window=self.long_window).mean()
                    long_sma_val = long_sma_series.iloc[-1]
                    if len(df_temp) >= self.long_window + 1:
                        prev_long_sma_val = long_sma_series.iloc[-2]

                log_data = {
                    'ltp': ltp, 'short_sma': short_sma_val, 'long_sma': long_sma_val,
                    'prev_short_sma': prev_short_sma_val, 'prev_long_sma': prev_long_sma_val,
                    'position_exists': self.portfolio.get_position(symbol) is not None
                }
                self._log_live_decision_data(symbol, timestamp, log_data)
            # --- END OF LOGGING BLOCK ---

            # The engine now provides the full, managed bar history directly.
            # We convert it to a DataFrame for easy calculation.
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
                    if ltp > 0:
                        quantity_to_buy = int(self.trade_value / ltp)
                        if quantity_to_buy > 0:
                            self.buy(symbol, quantity_to_buy, ltp, timestamp, is_live_trading)

                # Bearish Crossover
                elif short_sma < long_sma and prev_short_sma >= prev_long_sma and position and position['quantity'] > 0:
                    self.sell(symbol, abs(position['quantity']), ltp, timestamp, is_live_trading)