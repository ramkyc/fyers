# tests/strategies/test_opening_price_crossover.py

import sys
import os
import pytest
import pandas as pd
import datetime
from unittest.mock import MagicMock

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

    # Act
    strategy.on_data(timestamp, market_data)

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

    # Act
    strategy.on_data(timestamp, market_data)

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

    # Act
    strategy.on_data(timestamp, market_data)

    # Assert
    mock_order_manager.execute_order.assert_called_once()
    call_args = mock_order_manager.execute_order.call_args[0][0]
    assert call_args['action'] == 'SELL'
    assert call_args['quantity'] == 7
    assert call_args['price'] == 108.0
    assert strategy.active_trades['TEST.NSE']['t1_hit'] is True