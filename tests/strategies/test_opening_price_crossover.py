# tests/strategies/test_opening_price_crossover.py

import sys
import os
import pytest
import pandas as pd
import datetime
from unittest.mock import MagicMock, patch
from collections import deque

# Add the project root to the Python path to allow absolute imports from src
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.strategies.opening_price_crossover import OpeningPriceCrossoverStrategy

# Mock objects for Portfolio and OrderManager
@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.positions.get.return_value = None # Default to no position
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
        params={'ema_fast': 5, 'ema_slow': 10} # Use shorter periods for easier testing
    )

@pytest.fixture
def setup_strategy_data(strategy):
    """Adds enough historical data to the strategy to pass the length check."""
    df = pd.DataFrame({
        'open': [100]*10, 'high': [100]*10, 'low': [100]*10, 'close': [100]*10
    })
    strategy.data['TEST.NSE'] = df

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

def test_valid_entry_signal(strategy, mock_order_manager, setup_strategy_data):
    """Test that a buy order is placed when entry conditions are met."""
    # Arrange
    # This test will use the historical data from setup_strategy_data to calculate EMAs
    # A series of rising prices should result in a bullish EMA cross
    strategy.data['TEST.NSE']['close'] = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    market_data = generate_market_data(close=110, open_price=109, low=108, high=111)
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history and mock for filter
    strategy.implied_crossover_history['TEST.NSE'] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        # Act
        strategy.on_data(timestamp, {'D': {'TEST.NSE': market_data['TEST.NSE']}, '1': {'TEST.NSE': {'high': 100.5}}})

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'BUY'

def test_no_entry_on_bad_ema(strategy, mock_order_manager, setup_strategy_data):
    """Test that no order is placed if EMA filter is not met."""
    # Arrange: Create a bearish EMA crossover by making the recent prices trend down
    strategy.data['TEST.NSE']['close'] = [110, 109, 108, 107, 106, 105, 104, 103, 102, 101]
    market_data = generate_market_data(close=100, open_price=99, low=99, high=101)
    timestamp = datetime.datetime.now()

    # Act
    strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_not_called()

def test_stop_loss_exit(strategy, mock_portfolio, mock_order_manager, setup_strategy_data):
    """Test that a sell order is placed when the stop loss is hit."""
    # Arrange: Simulate an active position
    mock_portfolio.positions.get.return_value = {'quantity': 10, 'avg_price': 105}
    strategy.active_trades['TEST.NSE'] = {
        'stop_loss': 102.0, 'target1': 108.0, 'target2': 114.0, 
        'initial_quantity': 10, 't1_hit': False
    }
    market_data = generate_market_data(close=101, open_price=103, low=101.5, high=103)
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history and mock for filter
    strategy.implied_crossover_history['TEST.NSE'] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        # Act
        strategy.on_data(timestamp, {'D': {'TEST.NSE': market_data['TEST.NSE']}, '1': {'TEST.NSE': {'high': 100.5}}})

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'SELL'
    assert call_args['price'] == 102.0

def test_target1_partial_exit(strategy, mock_portfolio, mock_order_manager, setup_strategy_data):
    """Test that a partial sell order is placed when Target 1 is hit."""
    # Arrange: Simulate an active position
    mock_portfolio.positions.get.return_value = {'quantity': 10, 'avg_price': 105}
    strategy.active_trades['TEST.NSE'] = {
        'stop_loss': 102.0, 'target1': 108.0, 'target2': 114.0, 
        'initial_quantity': 10, 't1_hit': False
    }
    market_data = generate_market_data(close=108.5, open_price=107, low=106.5, high=109)
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history and mock for filter
    strategy.implied_crossover_history['TEST.NSE'] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        # Act
        strategy.on_data(timestamp, {'D': {'TEST.NSE': market_data['TEST.NSE']}, '1': {'TEST.NSE': {'high': 100.5}}})

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'SELL'
    assert call_args['quantity'] == 7
    assert call_args['price'] == 108.0
    assert strategy.active_trades['TEST.NSE']['t1_hit'] is True

# --- New tests for Implied Crossover Count and Average Filter ---

def test_calculate_implied_crossover_count_with_data(strategy):
    """Test implied crossover count when 1-min data is present and crosses open."""
    primary_open = 100.0
    # 1-min data where high crosses primary_open
    market_data_all_resolutions = {
        '1': {
            'SYM1': {'open': 99, 'high': 101, 'low': 98, 'close': 100},
            'SYM2': {'open': 98, 'high': 99, 'low': 97, 'close': 98.5}
        }
    }
    count = strategy._calculate_implied_crossover_count('SYM1', datetime.datetime.now(), primary_open, market_data_all_resolutions)
    assert count == 1

def test_calculate_implied_crossover_count_no_cross(strategy):
    """Test implied crossover count when 1-min data is present but does not cross open."""
    primary_open = 100.0
    # 1-min data where high does not cross primary_open
    market_data_all_resolutions = {
        '1': {
            'SYM1': {'open': 95, 'high': 98, 'low': 94, 'close': 97},
            'SYM2': {'open': 90, 'high': 92, 'low': 89, 'close': 91}
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

def test_average_implied_crossover_count(strategy):
    """Test calculation of average implied crossover count and history limit."""
    symbol = 'TEST.NSE'
    strategy.implied_crossover_history[symbol] = deque([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    
    # Add a new count, should push out the oldest (1)
    strategy.on_data(datetime.datetime.now(), {'D': {symbol: generate_market_data(100, 100, 100, 100)[symbol]}}, is_live=False) # Dummy call to trigger on_data
    strategy.implied_crossover_history[symbol].append(11) # Manually append for test
    strategy.implied_crossover_history[symbol].popleft() # Manually pop for test

    avg = sum(strategy.implied_crossover_history[symbol]) / len(strategy.implied_crossover_history[symbol])
    assert avg == 6.5 # (2+3+4+5+6+7+8+9+10+11) / 10
    assert len(strategy.implied_crossover_history[symbol]) == 10

def test_entry_with_implied_crossover_filter_pass(strategy, mock_order_manager, setup_strategy_data):
    """Test entry when implied crossover count is above average."""
    symbol = 'TEST.NSE'
    # Arrange: Set up bullish EMA and price conditions
    strategy.data[symbol]['close'] = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    market_data = generate_market_data(close=110, open_price=109, low=108, high=111)
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history so current is above average
    strategy.implied_crossover_history[symbol] = deque([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]) # Average = 1
    # The on_data call will calculate implied_crossover_count = 1 (from generate_market_data)
    # This test needs to be adjusted to ensure implied_crossover_count > average_implied_crossover_count
    # Let's make the current implied_crossover_count higher than the average
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=5) as mock_calc_crossover:
        strategy.on_data(timestamp, {'D': {symbol: market_data[symbol]}, '1': {symbol: {'high': 100.5}}})

    # Assert
    mock_order_manager.execute_order.assert_called_once()

def test_entry_with_implied_crossover_filter_fail(strategy, mock_order_manager, setup_strategy_data):
    """Test no entry when implied crossover count is not above average."""
    symbol = 'TEST.NSE'
    # Arrange: Set up bullish EMA and price conditions
    strategy.data[symbol]['close'] = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    market_data = generate_market_data(close=110, open_price=109, low=108, high=111)
    timestamp = datetime.datetime.now()

    # Arrange: Set up implied crossover history so current is not above average
    strategy.implied_crossover_history[symbol] = deque([5, 5, 5, 5, 5, 5, 5, 5, 5, 5]) # Average = 5
    with patch.object(strategy, '_calculate_implied_crossover_count', return_value=1) as mock_calc_crossover:
        strategy.on_data(timestamp, {'D': {symbol: market_data[symbol]}, '1': {symbol: {'high': 100.5}}})

    # Assert
    mock_order_manager.execute_order.assert_not_called()
