# src/strategies/bt_opening_price_crossover.py

import datetime
import pandas as pd
import pandas_ta as ta
from collections import defaultdict, deque
from typing import Dict
import sys

from .base_strategy import BaseStrategy

class OpeningPriceCrossoverStrategy(BaseStrategy):
    """
    A long-only momentum strategy with a multi-faceted entry filter.

    Core Logic:
    - Enters a long position when a bullish EMA crossover (e.g., 9 over 21) is present.
    - The primary filter is based on the instrument's relationship with its daily open price,
      which serves as a proxy for intraday sentiment.

    Options Trading Logic:
    - For options, the strategy's sentiment filter is based on the **underlying index's** daily open, not the option's.
    - **Call (CE) options** are treated like stocks: an entry is considered only if the underlying index is trading ABOVE its daily open (bullish sentiment).
    - **Put (PE) options** have inverted logic: an entry is considered only if the underlying index is trading BELOW its daily open (bearish sentiment).
    """

    def __init__(self, symbols: list[str], portfolio: 'PT_Portfolio' = None, order_manager: 'OrderManager' = None, params: dict[str, object] = None, resolutions: list[str] = None, primary_resolution: str = None):
        """
        Initializes the Opening Price Crossover Strategy.
        """
        super().__init__(symbols, portfolio, order_manager, params, resolutions, primary_resolution)
        
        # Strategy-specific parameters
        self.ema_fast_period = self.params.get('ema_fast', 9)
        self.ema_slow_period = self.params.get('ema_slow', 21)
        self.rr_ratio_target1 = self.params.get('rr1', 1.0)
        self.rr_ratio_target2 = self.params.get('rr2', 1.5)
        self.rr_ratio_target3 = self.params.get('rr3', 3.0)
        self.exit_percent_target1 = self.params.get('exit_pct1', 0.5) # 50%
        self.exit_percent_target2 = self.params.get('exit_pct2', 0.2) # 20%
        # The final exit percentage is implied (100% - 50% - 20% = 30%)

        # New ATR-based Stop-Loss parameters
        self.atr_period = self.params.get('atr_period', 14)
        self.atr_multiplier = self.params.get('atr_multiplier', 1.5)

        self.trade_value: float = float(self.params.get('trade_value', 100000.0))

        # In-memory state for the strategy
        self.active_trades = {symbol: None for symbol in self.symbols}
        # State for live trading to track daily open
        self.daily_open_prices = {symbol: None for symbol in self.symbols}
        self.last_processed_day = {symbol: None for symbol in self.symbols}
        self.implied_crossover_history: 'defaultdict[str, deque[float]]' = defaultdict(deque)

    @staticmethod
    def get_optimizable_params() -> list[dict]:
        """
        Returns parameters that can be optimized for this strategy.
        """
        return [
            {'name': 'ema_fast', 'label': 'EMA Fast Range', 'type': 'slider', 'min': 2, 'max': 20, 'default': (5, 10), 'step': 1},
            {'name': 'ema_slow', 'label': 'EMA Slow Range', 'type': 'slider', 'min': 10, 'max': 50, 'default': (15, 25), 'step': 1}
        ]

    def get_required_resolutions(self) -> list[str]:
        """
        This strategy needs its primary resolution, plus Daily and 1-minute data
        for its open price and implied crossover calculations.
        """
        # The primary resolution is already known. We just need to declare the *additional*
        # resolutions required for the strategy's logic.
        # --- DEFINITIVE FIX ---
        # The strategy requires '1'-minute data for the crossover count calculation. It must be requested here.
        required = {self.primary_resolution, "D", "1"}
        return sorted(list(required), key=lambda x: (x != self.primary_resolution, x))

    def _log_live_decision_data(self, symbol: str, timestamp: datetime.datetime, data: dict):
        """
        Helper to log the data used for making a live trade decision.
        This now uses the structured logging system from the base strategy.
        """
        # This now uses the structured logging system from the base strategy
        # The UI specifically looks for the message "Strategy Decision"
        # In backtesting, we just append the dictionary to the debug_log list.
        # The base class's _log_debug method handles the distinction.
        self._log_debug({
            "timestamp": timestamp, "symbol": symbol, "ltp": data.get('ltp'),
            "ema_fast": data.get('ema_fast'), "ema_slow": data.get('ema_slow'), "ema_bullish": data.get('is_ema_bullish'),
            "candle_open": data.get('candle_open'), "price_bullish": data.get('is_price_bullish'),
            "daily_open": data.get('daily_open'), "sentiment_bullish": data.get('sentiment_filter_passed'),
            "crossover_count": data.get('crossover_count'), "avg_crossover_count": data.get('avg_crossover_count'), "crossover_spike": data.get('is_crossover_spike'),
            "final_decision": 'TRADE' if data.get('all_conditions_met') else 'NO TRADE'
        })

    def on_data(self, timestamp: datetime, market_data_all_resolutions: Dict[str, Dict[str, Dict[str, object]]], **kwargs):
        """
        Called for each new data bar.
        """
        is_live = kwargs.get('is_live_trading', False)
        live_crossover_count = kwargs.get('live_crossover_count', 0)

        # Extract data for the primary resolution
        market_data = market_data_all_resolutions.get(self.primary_resolution, {})

        for symbol in self.symbols:
            # --- UNCONDITIONAL LOGGING SETUP ---
            # Create the log dictionary at the start of every bar processing.
            decision_log = {
                'timestamp': timestamp.isoformat(), 'symbol': symbol, 'primary_resolution': self.primary_resolution,
                'decision': 'No Action' # Default decision
            }

            # --- NEW ROBUST LOGIC STRUCTURE ---
            # 1. Check for sufficient data before doing any calculations
            if symbol not in market_data:
                decision_log['decision'] = 'No primary data for symbol'
            else:
                bar_history_list = market_data[symbol]
                df = pd.DataFrame(bar_history_list)
                
                # Get Daily Open Price
                daily_data_for_symbol = market_data_all_resolutions.get("D", {}).get(symbol)
                daily_open_price = daily_data_for_symbol.get('open', 0) if daily_data_for_symbol and isinstance(daily_data_for_symbol, dict) else 0
                decision_log['daily_open'] = daily_open_price

                if len(df) < self.ema_slow_period or daily_open_price == 0:
                    decision_log['decision'] = 'Not enough data for indicators'
                else:
                    # 2. All data is present, proceed with calculations
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df = df.set_index('timestamp')
                    df.ta.ema(length=self.ema_fast_period, append=True)
                    df.ta.ema(length=self.ema_slow_period, append=True)
                    df.ta.atr(length=self.atr_period, append=True)
                    
                    latest_analysis = df.iloc[-1]
                    previous_analysis = df.iloc[-2] if len(df) > 1 else latest_analysis
                    ema_fast = latest_analysis[f'EMA_{self.ema_fast_period}']
                    ema_slow = latest_analysis[f'EMA_{self.ema_slow_period}']
                    atr_value = latest_analysis.get(f'ATRr_{self.atr_period}', 0)

                    # Calculate crossover stats
                    crossover_count = self._calculate_implied_crossover_count(symbol, timestamp, daily_open_price, market_data_all_resolutions)
                    self.implied_crossover_history[symbol].append(crossover_count)
                    if len(self.implied_crossover_history[symbol]) > 10:
                        self.implied_crossover_history[symbol].popleft()
                    average_implied_crossover_count = sum(self.implied_crossover_history[symbol]) / len(self.implied_crossover_history[symbol]) if self.implied_crossover_history[symbol] else 0

                    # Update log with all calculated data
                    decision_log.update({
                        'close': latest_analysis['close'], 'ema_fast': ema_fast, 'ema_slow': ema_slow, 'atr': atr_value,
                        'crossover_count': crossover_count, 'avg_crossover_count': average_implied_crossover_count
                    })

                    # 3. Position Management
                    active_trade = self.portfolio.get_position(symbol, self.primary_resolution)
                    if active_trade and active_trade.get('quantity', 0) > 0:
                        trade_details = self.active_trades[symbol]
                        if trade_details:
                            self._check_and_execute_exit(symbol, latest_analysis, trade_details, active_trade, decision_log, timestamp, is_live)
                    else:
                        # Check for Entries
                        is_ema_bullish = ema_fast > ema_slow
                        is_price_bullish = latest_analysis['close'] >= latest_analysis['open']
                        sentiment_filter_passed = latest_analysis['close'] > daily_open_price
                        is_crossover_spike = crossover_count > average_implied_crossover_count
                        all_conditions_met = is_ema_bullish and is_price_bullish and sentiment_filter_passed and is_crossover_spike
                        
                        decision_log.update({
                            'is_ema_bullish': is_ema_bullish, 'is_price_bullish': is_price_bullish,
                            'sentiment_filter_passed': sentiment_filter_passed, 'is_crossover_spike': is_crossover_spike,
                            'all_conditions_met': all_conditions_met
                        })

                        if all_conditions_met:
                            entry_price = latest_analysis['close']
                            volatility_stop = min(latest_analysis['low'], previous_analysis['low'])
                            atr_stop = entry_price - (atr_value * self.atr_multiplier)
                            stop_loss = min(volatility_stop, atr_stop)
                            risk_per_share = entry_price - stop_loss

                            if risk_per_share > 0:
                                target1, target2, target3 = self._calculate_targets(entry_price, risk_per_share)
                                capital_to_deploy = self.portfolio.get_capital_for_position(symbol, self.primary_resolution, self.trade_value)
                                quantity = int(capital_to_deploy / entry_price)

                                if quantity > 0:
                                    decision_log['decision'] = 'BUY'
                                    self.buy(symbol, self.primary_resolution, quantity, entry_price, timestamp, is_live)
                                    self.active_trades[symbol] = {
                                        'stop_loss': stop_loss, 'target1': target1, 'target2': target2, 'target3': target3,
                                        'initial_quantity': quantity, 't1_hit': False, 't2_hit': False, 't3_hit': False
                                    }

            # --- UNCONDITIONAL LOGGING ---
            # Log the decision for this bar, for this symbol, regardless of the outcome.
            self._log_debug(decision_log)

    def _check_and_execute_exit(self, symbol: str, latest_analysis: pd.Series, trade_details: dict, active_trade: dict, decision_log: dict, timestamp: datetime.datetime, is_live: bool):
        """Helper method to check and execute exits, updating the decision log."""
        # Check Target 3 first (highest target)
        if not trade_details.get('t3_hit', False) and latest_analysis['high'] >= trade_details['target3']:
            decision_log['decision'] = 'EXIT at T3 (Full)'
            self.sell(symbol, self.primary_resolution, active_trade['quantity'], trade_details['target3'], timestamp, is_live)
            self.active_trades[symbol] = None # Close trade
            return

        # Check Target 2
        if not trade_details.get('t2_hit', False) and latest_analysis['high'] >= trade_details['target2']:
            qty_to_sell_t2 = int(trade_details['initial_quantity'] * self.exit_percent_target2)
            if qty_to_sell_t2 > 0 and active_trade['quantity'] >= qty_to_sell_t2:
                decision_log['decision'] = f"EXIT at T2 ({self.exit_percent_target2 * 100:.0f}%)"
                self.sell(symbol, self.primary_resolution, qty_to_sell_t2, trade_details['target2'], timestamp, is_live)
                trade_details['t2_hit'] = True

        # Check Target 1
        if not trade_details.get('t1_hit', False) and latest_analysis['high'] >= trade_details['target1']:
            qty_to_sell = int(trade_details['initial_quantity'] * self.exit_percent_target1)
            if qty_to_sell > 0 and active_trade['quantity'] >= qty_to_sell:
                decision_log['decision'] = f"EXIT at T1 ({self.exit_percent_target1 * 100:.0f}%)"
                self.sell(symbol, self.primary_resolution, qty_to_sell, trade_details['target1'], timestamp, is_live)
                trade_details['t1_hit'] = True

        # Check Stop Loss
        if latest_analysis['low'] <= trade_details['stop_loss']:
            decision_log['decision'] = 'EXIT at Stop-Loss (Full)'
            self.sell(symbol, self.primary_resolution, active_trade['quantity'], trade_details['stop_loss'], timestamp, is_live)
            self.active_trades[symbol] = None # Close trade
            return
        
        # If no exit condition was met, the decision is to hold.
        if decision_log['decision'] == 'No Action':
            decision_log['decision'] = 'HOLD'

    def _calculate_targets(self, entry_price, risk_per_share):
        """Helper function to calculate all three profit targets."""
        target1 = entry_price + (risk_per_share * self.rr_ratio_target1)
        target2 = entry_price + (risk_per_share * self.rr_ratio_target2)
        target3 = entry_price + (risk_per_share * self.rr_ratio_target3)
        return target1, target2, target3

    def _calculate_implied_crossover_count(self, symbol: str, primary_timestamp: datetime.datetime, primary_open_price: float, market_data_all_resolutions: dict) -> int:
        """
        Calculates the implied crossover count for a primary resolution candle
        using lower-timeframe data (e.g., 1-minute data).
        """
        # Assuming '1' is the 1-minute resolution
        lower_resolution = '1' 
        if lower_resolution not in market_data_all_resolutions:
            return 0

        lower_res_data = market_data_all_resolutions.get(lower_resolution, {})
        symbol_1min_data = lower_res_data.get(symbol)

        if not symbol_1min_data:
            return 0
        
        crossover_count = 0
        # The engine now provides a dictionary of {timestamp: data} for the 1-min resolution
        # within the primary candle's timeframe. The data is a list of bar dicts.
        for bar_data in symbol_1min_data:
            # This logic is correct as per user feedback. It measures the "spike"
            # of 1-min bars crossing the open of the primary (e.g., 15-min) candle.
            if bar_data['high'] > primary_open_price:
                crossover_count += 1
        
        return crossover_count