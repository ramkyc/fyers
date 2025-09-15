# tests/strategies/test_simple_ma_crossover.py

import pytest
import datetime
import pandas as pd
import sys # Add the project root to the Python path to allow absolute imports
import os
from unittest.mock import MagicMock, ANY

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.strategies.simple_ma_crossover import SMACrossoverStrategy

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
        params={'short_window': 3, 'long_window': 5, 'trade_quantity': 10}
    )

def generate_test_data(prices):
    start_date = datetime.datetime(2025, 1, 1)
    dates = [start_date + datetime.timedelta(days=i) for i in range(len(prices))]
    return pd.DataFrame(prices, index=dates, columns=["TEST:STOCK-EQ"])

def test_buy_signal_on_bullish_crossover(strategy_instance, mock_portfolio, mock_order_manager):
    # Prices are crafted to create a bullish crossover at the last data point
    # Short SMA (3-day) crosses above Long SMA (5-day)
    prices = [100, 100, 100, 100, 100, 105, 110, 115] # Short SMA crosses above Long SMA at 105
    test_data = generate_test_data(prices)

    for timestamp, row in test_data.iterrows():
        strategy_instance.on_data(timestamp, {"TEST:STOCK-EQ": {'close': row["TEST:STOCK-EQ"]}})

    mock_order_manager.execute_order.assert_called_once()

def test_sell_signal_on_bearish_crossover(strategy_instance, mock_portfolio, mock_order_manager):
    mock_portfolio.get_position.return_value = {'quantity': 10} # Simulate having a position
    # Prices are crafted to create a bearish crossover at the last data point
    # Short SMA (3-day) crosses below Long SMA (5-day)
    # Previous state: Short SMA > Long SMA
    # Current state: Short SMA < Long SMA
    prices = [100, 105, 110, 105, 100, 95, 90, 85] # Bearish crossover at 95
    test_data = generate_test_data(prices)

    for timestamp, row in test_data.iterrows():
        strategy_instance.on_data(timestamp, {"TEST:STOCK-EQ": {'close': row["TEST:STOCK-EQ"]}})

    mock_order_manager.execute_order.assert_called_once()