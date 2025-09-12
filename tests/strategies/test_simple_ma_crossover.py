# tests/strategies/test_simple_ma_crossover.py

import pytest
import datetime
import pandas as pd
from unittest.mock import MagicMock, ANY

from strategies.simple_ma_crossover import SMACrossoverStrategy

@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_position.return_value = None
    return portfolio

@pytest.fixture
def mock_order_manager():
    return MagicMock()

@pytest.fixture
def strategy_instance(mock_portfolio, mock_order_manager):
    return SMACrossoverStrategy(
        symbols=["TEST:STOCK-EQ"],
        portfolio=mock_portfolio,
        order_manager=mock_order_manager,
        params={'short_window': 3, 'long_window': 5, 'trade_value': 10000},
        resolutions=['D']
    )

def generate_bar_history(prices):
    """Helper to create a list of bar history dictionaries."""
    start_time = datetime.datetime(2025, 1, 1, 9, 15)
    return [
        {'timestamp': start_time + datetime.timedelta(days=i), 'open': p, 'high': p+1, 'low': p-1, 'close': p, 'volume': 100}
        for i, p in enumerate(prices)
    ]

def test_buy_signal_on_bullish_crossover(strategy_instance, mock_portfolio, mock_order_manager):
    # Prices are crafted to create a bullish crossover at the last data point
    # Short SMA (3-day) crosses above Long SMA (5-day)
    prices = [100, 100, 100, 100, 100, 100, 100, 110] # Creates a clean crossover at the last point
    bar_history = generate_bar_history(prices)
    timestamp = bar_history[-1]['timestamp']
    market_data = {'D': {'TEST:STOCK-EQ': bar_history}}

    strategy_instance.on_data(timestamp, market_data)

    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'BUY'
    assert call_args['timeframe'] == 'D'

def test_sell_signal_on_bearish_crossover(strategy_instance, mock_portfolio, mock_order_manager):
    mock_portfolio.get_position.return_value = {'quantity': 10} # Simulate having a position
    # Prices are crafted to create a bearish crossover at the last data point
    # Short SMA (3-day) crosses below Long SMA (5-day)
    # Previous state: Short SMA > Long SMA
    # Current state: Short SMA < Long SMA
    prices = [100, 101, 102, 103, 104, 105, 100, 95] # Creates a clean bearish crossover
    bar_history = generate_bar_history(prices)
    timestamp = bar_history[-1]['timestamp']
    market_data = {'D': {'TEST:STOCK-EQ': bar_history}}

    strategy_instance.on_data(timestamp, market_data)

    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'SELL'
    assert call_args['timeframe'] == 'D'