# src/strategies/simple_ma_crossover.py

from collections import defaultdict
import pandas as pd
from src.paper_trading.oms import OrderManager
from src.paper_trading.portfolio import Portfolio
from .base_strategy import BaseStrategy
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


    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates trading signals for all symbols based on historical data.
        This is a vectorized operation.

        Args:
            data (pd.DataFrame): A DataFrame with a MultiIndex (timestamp, symbol)
                                 and a 'close' column.

        Returns:
            pd.DataFrame: The input DataFrame with an added 'signal' column.
                          (1 for Buy, -1 for Sell, 0 for Hold).
        """
        signals_df = data.copy()
        signals_df['signal'] = 0

        # Group by symbol to calculate indicators for each symbol independently
        grouped = signals_df.groupby('symbol')['close']
        
        # Calculate SMAs
        short_sma = grouped.transform(lambda x: x.rolling(window=self.short_window).mean())
        long_sma = grouped.transform(lambda x: x.rolling(window=self.long_window).mean())

        # Create a 'signal' column: 1 for bullish crossover, -1 for bearish
        # np.where is a fast, vectorized conditional assignment
        signals_df['signal'] = np.where(short_sma > long_sma, 1, 0)
        signals_df['signal'] = np.where(short_sma < long_sma, -1, signals_df['signal'])

        # Generate trading orders based on the change in signal
        # .diff() calculates the difference from the previous row (within each group)
        # A change from -1 to 1 is a BUY signal (diff=2)
        # A change from 1 to -1 is a SELL signal (diff=-2)
        signals_df['positions'] = signals_df.groupby('symbol')['signal'].diff()

        return signals_df

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
                position = self.portfolio.get_position(symbol)

                # Bullish Crossover
                if short_sma > long_sma and prev_short_sma <= prev_long_sma and not position:
                    print(f"LIVE SIGNAL: Bullish crossover for {symbol}. Placing BUY order.")
                    self.order_manager.execute_order({'symbol': symbol, 'action': 'BUY', 'quantity': self.trade_quantity, 'price': ltp, 'timestamp': timestamp}, is_live_trading=is_live_trading)

                # Bearish Crossover
                elif short_sma < long_sma and prev_short_sma >= prev_long_sma and position:
                    print(f"LIVE SIGNAL: Bearish crossover for {symbol}. Placing SELL order.")
                    self.order_manager.execute_order({'symbol': symbol, 'action': 'SELL', 'quantity': abs(position['quantity']), 'price': ltp, 'timestamp': timestamp}, is_live_trading=is_live_trading)

            self.short_sma[symbol] = short_sma
            self.long_sma[symbol] = long_sma