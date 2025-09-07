# src/strategies/opening_price_crossover.py

import datetime
import pandas as pd
import pandas_ta as ta

from src.strategies.base_strategy import BaseStrategy

class OpeningPriceCrossoverStrategy(BaseStrategy):
    """
    A long-only strategy that enters when the price crosses above the candle's open,
    filtered by a 9/21 EMA crossover.
    """

    def __init__(self, symbols: list[str], portfolio: 'Portfolio', order_manager: 'OrderManager', params: dict[str, object] = None):
        """
        Initializes the Opening Price Crossover Strategy.
        """
        super().__init__(symbols, portfolio, order_manager, params)
        
        # Strategy-specific parameters
        self.ema_fast_period = self.params.get('ema_fast', 9)
        self.ema_slow_period = self.params.get('ema_slow', 21)
        self.rr_ratio_target1 = self.params.get('rr1', 1.0)
        self.rr_ratio_target2 = self.params.get('rr2', 3.0)
        self.exit_percent_target1 = self.params.get('exit_pct1', 0.7) # 70%

        # In-memory state for the strategy
        self.data = {symbol: pd.DataFrame() for symbol in self.symbols}
        self.active_trades = {symbol: None for symbol in self.symbols}

    @staticmethod
    def get_optimizable_params() -> list[dict]:
        """
        Returns parameters that can be optimized for this strategy.
        """
        return [
            {'name': 'ema_fast', 'type': 'slider', 'min': 2, 'max': 20, 'default': (5, 10), 'step': 1},
            {'name': 'ema_slow', 'type': 'slider', 'min': 10, 'max': 50, 'default': (15, 25), 'step': 1}
        ]

    def on_data(self, timestamp: datetime, market_data: dict[str, dict[str, object]], **kwargs):
        """
        Called for each new data bar.
        """
        is_live = kwargs.get('is_live_trading', False)

        for symbol in self.symbols:
            if symbol not in market_data:
                continue

            # Append new data
            new_data = market_data[symbol]
            new_row = pd.DataFrame([new_data], index=[timestamp])
            self.data[symbol] = pd.concat([self.data[symbol], new_row])
            df = self.data[symbol]

            # Ensure we have enough data to calculate indicators
            if len(df) < self.ema_slow_period:
                continue

            # --- Indicator Calculations ---
            df.ta.ema(length=self.ema_fast_period, append=True)
            df.ta.ema(length=self.ema_slow_period, append=True)
            
            # Get the latest values
            latest = df.iloc[-1]
            previous = df.iloc[-2] if len(df) > 1 else latest
            
            ema_fast = latest[f'EMA_{self.ema_fast_period}']
            ema_slow = latest[f'EMA_{self.ema_slow_period}']

            # --- Position Management ---
            active_trade = self.portfolio.positions.get(symbol)
            
            # 1. Check for Exits if a position is open
            if active_trade and active_trade['quantity'] > 0:
                trade_details = self.active_trades[symbol]
                if not trade_details: continue # Should not happen if position is active

                # Check Target 2 first
                if latest['high'] >= trade_details['target2']:
                    print(f"{timestamp} | {symbol} | EXIT T2: Selling remaining {active_trade['quantity']} shares at {trade_details['target2']}")
                    self.sell(symbol, active_trade['quantity'], trade_details['target2'], timestamp, is_live)
                    self.active_trades[symbol] = None # Close trade
                    continue

                # Check Target 1
                if not trade_details['t1_hit'] and latest['high'] >= trade_details['target1']:
                    qty_to_sell = int(trade_details['initial_quantity'] * self.exit_percent_target1)
                    if qty_to_sell > 0:
                        print(f"{timestamp} | {symbol} | EXIT T1: Selling {qty_to_sell} shares at {trade_details['target1']}")
                        self.sell(symbol, qty_to_sell, trade_details['target1'], timestamp, is_live)
                        trade_details['t1_hit'] = True

                # Check Stop Loss
                if latest['low'] <= trade_details['stop_loss']:
                    print(f"{timestamp} | {symbol} | EXIT SL: Selling remaining {active_trade['quantity']} shares at {trade_details['stop_loss']}")
                    self.sell(symbol, active_trade['quantity'], trade_details['stop_loss'], timestamp, is_live)
                    self.active_trades[symbol] = None # Close trade
                    continue
            
            # 2. Check for Entries if no position is open
            else:
                # --- Entry Conditions ---
                is_ema_bullish = ema_fast > ema_slow
                is_price_bullish = latest['close'] > latest['open']

                if is_ema_bullish and is_price_bullish:
                    entry_price = latest['close']
                    stop_loss = min(latest['low'], previous['low'])
                    risk_per_share = entry_price - stop_loss

                    if risk_per_share <= 0: continue

                    target1 = entry_price + (risk_per_share * self.rr_ratio_target1)
                    target2 = entry_price + (risk_per_share * self.rr_ratio_target2)
                    
                    # Simple quantity calculation
                    cash_per_symbol = self.portfolio.initial_cash / len(self.symbols)
                    quantity = int(cash_per_symbol / entry_price)

                    if quantity > 0:
                        print(f"{timestamp} | {symbol} | ENTRY: Buying {quantity} shares at {entry_price:.2f}")
                        self.buy(symbol, quantity, entry_price, timestamp, is_live)
                        self.active_trades[symbol] = {
                            'stop_loss': stop_loss,
                            'target1': target1,
                            'target2': target2,
                            'initial_quantity': quantity,
                            't1_hit': False
                        }
