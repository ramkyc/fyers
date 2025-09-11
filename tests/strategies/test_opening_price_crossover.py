# tests/strategies/test_opening_price_crossover.py

import pytest
import pandas as pd
import datetime
from unittest.mock import MagicMock, patch
from collections import deque

from strategies.opening_price_crossover import OpeningPriceCrossoverStrategy

# Mock objects for Portfolio and OrderManager
@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_position.return_value = None # Default to no position
    portfolio.initial_cash = 100000
    return portfolio

@pytest.fixture
def mock_order_manager():
    return MagicMock()

@pytest.fixture
def strategy(mock_portfolio, mock_order_manager):
    """Initializes the strategy with mock objects."""
    return OpeningPriceCrossoverStrategy(
        symbols=['TEST.NSE'],
        portfolio=mock_portfolio,
        order_manager=mock_order_manager,
        params={'ema_fast': 5, 'ema_slow': 10}, # Use shorter periods for easier testing
        resolutions=['15'] # Set a primary resolution for testing
    )

def generate_market_data(close, open_price, low, high):
    """Helper to create a single data point."""
    return {
        'TEST.NSE': {
            'close': close,
            'open': open_price,
            'low': low,
            'high': high
        }
    }

def generate_bar_history(prices):
    """Helper to create a list of bar history dictionaries."""
    start_time = datetime.datetime(2025, 1, 1, 9, 15)
    # Generate enough data points to satisfy the default ATR period (14) + buffer
    return [ 
        {'timestamp': start_time + datetime.timedelta(minutes=i), 'open': p, 'high': p+1, 'low': p-1, 'close': p, 'volume': 100}
        for i, p in enumerate(prices)
    ]

def test_valid_entry_signal(strategy, mock_order_manager):
    """Test that a buy order is placed when entry conditions are met."""
    # Arrange
    # A series of rising prices should result in a bullish EMA cross. Make the last candle bullish.
    bar_history = generate_bar_history([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115])
    market_data = {'15': {'TEST.NSE': bar_history}}
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history and mock for filter
    strategy.implied_crossover_history['TEST.NSE'] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        # Act
        strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'BUY'
    assert call_args['timeframe'] == '15'

def test_no_entry_on_bad_ema(strategy, mock_order_manager):
    """Test that no order is placed if EMA filter is not met."""
    # Arrange: Create a bearish EMA crossover by making the recent prices trend down
    bar_history = generate_bar_history([115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100])
    market_data = {'15': {'TEST.NSE': bar_history}}
    timestamp = datetime.datetime.now()

    # Act
    strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_not_called()

def test_stop_loss_exit(strategy, mock_portfolio, mock_order_manager):
    """Test that a sell order is placed when the stop loss is hit."""
    # Arrange: Simulate an active position
    mock_portfolio.get_position.return_value = {'quantity': 10, 'avg_price': 105}
    strategy.active_trades['TEST.NSE'] = {
        'stop_loss': 102.0, 'target1': 108.0, 'target2': 114.0, 'target3': 120.0,
        'initial_quantity': 10, 't1_hit': False, 't2_hit': False
    }
    bar_history = generate_bar_history([115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101.5])
    market_data = {'15': {'TEST.NSE': bar_history}}
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history and mock for filter
    strategy.implied_crossover_history['TEST.NSE'] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        # Act
        strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'SELL'
    assert call_args['price'] == 102.0
    assert call_args['timeframe'] == '15'

def test_target1_partial_exit(strategy, mock_portfolio, mock_order_manager):
    """Test that a partial sell order is placed when Target 1 is hit."""
    # Arrange: Simulate an active position
    mock_portfolio.get_position.return_value = {'quantity': 10, 'avg_price': 105}
    strategy.active_trades['TEST.NSE'] = {
        'stop_loss': 102.0, 'target1': 108.0, 'target2': 114.0, 'target3': 120.0,
        'initial_quantity': 10, 't1_hit': False, 't2_hit': False
    }
    bar_history = generate_bar_history([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 108.5])
    market_data = {'15': {'TEST.NSE': bar_history}}
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history and mock for filter
    strategy.implied_crossover_history['TEST.NSE'] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        # Act
        strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'SELL'
    assert call_args['quantity'] == 5 # 50% of 10
    assert call_args['price'] == 108.0
    assert strategy.active_trades['TEST.NSE']['t1_hit'] is True

# --- New tests for Implied Crossover Count and Average Filter ---

def test_calculate_implied_crossover_count_with_data(strategy):
    """Test implied crossover count when 1-min data is present and crosses open."""
    primary_open = 100.0
    # 1-min data where high crosses primary_open
    one_min_bars = [{'high': 101}, {'high': 99}, {'high': 102}]
    market_data_all_resolutions = {
        '1': {
            'SYM1': one_min_bars,
            'SYM2': [{'high': 99}]
        }
    }
    count = strategy._calculate_implied_crossover_count('SYM1', datetime.datetime.now(), primary_open, market_data_all_resolutions)
    assert count == 2

def test_calculate_implied_crossover_count_no_cross(strategy):
    """Test implied crossover count when 1-min data is present but does not cross open."""
    primary_open = 100.0
    # 1-min data where high does not cross primary_open
    one_min_bars = [{'high': 98}, {'high': 99}]
    market_data_all_resolutions = {
        '1': {
            'SYM1': one_min_bars
        }
    }
    count = strategy._calculate_implied_crossover_count('SYM1', datetime.datetime.now(), primary_open, market_data_all_resolutions)
    assert count == 0

def test_calculate_implied_crossover_count_no_1min_data(strategy):
    """Test implied crossover count when 1-min data is missing."""
    primary_open = 100.0
    market_data_all_resolutions = {
        '5': {
            'SYM1': {'open': 99, 'high': 101, 'low': 98, 'close': 100}
        }
    }
    count = strategy._calculate_implied_crossover_count('SYM1', datetime.datetime.now(), primary_open, market_data_all_resolutions)
    assert count == 0

def test_entry_with_implied_crossover_filter_pass(strategy, mock_order_manager):
    """Test entry when implied crossover count is above average."""
    symbol = 'TEST.NSE'
    # Arrange: Set up bullish EMA and price conditions
    bar_history = generate_bar_history([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115])
    market_data = {'15': {symbol: bar_history}}
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history so current is above average
    strategy.implied_crossover_history[symbol] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    # The on_data call will calculate implied_crossover_count = 1 (from generate_market_data)
    # This test needs to be adjusted to ensure implied_crossover_count > average_implied_crossover_count
    # Let's make the current implied_crossover_count higher than the average
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_called_once()

def test_entry_with_implied_crossover_filter_fail(strategy, mock_order_manager):
    """Test no entry when implied crossover count is not above average."""
    symbol = 'TEST.NSE'
    # Arrange: Set up bullish EMA and price conditions
    bar_history = generate_bar_history([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115])
    market_data = {'15': {symbol: bar_history}}
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history so current is not above average
    strategy.implied_crossover_history[symbol] = deque([5, 5, 5, 5, 5, 5, 5, 5, 5, 5]) # Average = 5
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=1) as mock_calc_crossover:
        strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_not_called()
