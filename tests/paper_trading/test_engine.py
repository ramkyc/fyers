# tests/paper_trading/test_engine.py

import pytest
import datetime
from unittest.mock import MagicMock, patch, ANY
from collections import defaultdict

from paper_trading.engine import LiveTradingEngine
from strategies.base_strategy import BaseStrategy

# --- Mocks and Fixtures ---

@pytest.fixture
def mock_fyers_model():
    return MagicMock()

@pytest.fixture
def mock_strategy():
    strategy = MagicMock(spec=BaseStrategy)
    strategy.params = {} # Mock the params attribute
    return strategy

@pytest.fixture
def engine(mock_fyers_model, mock_strategy):
    """Provides a LiveTradingEngine instance with mocked dependencies."""
    # We patch the super().__init__ call to avoid dealing with its side effects (like file I/O)
    with patch('fyers_apiv3.FyersWebsocket.data_ws.FyersDataSocket.__init__', return_value=None):
        eng = LiveTradingEngine(
            fyers_model=mock_fyers_model,
            app_id="test_app_id",
            access_token="test_token",
            strategies=[mock_strategy], # Pass a list containing the mock strategy
            initial_cash=100000.0
        )
    return eng

# Helper to create a tick message
def create_tick_message(symbol, ltp, timestamp_epoch):
    return [{'symbol': symbol, 'ltp': ltp, 'timestamp': timestamp_epoch}]

# --- Test Cases ---

def test_crossover_count_initialization(engine):
    """Test that the first tick sets the open price and count is zero."""
    # Arrange
    symbol = "TEST.NSE"
    timestamp = int(datetime.datetime.now().timestamp())
    message = create_tick_message(symbol, 100.0, timestamp)

    # Act
    engine.on_message(message)

    # Assert
    assert engine.live_daily_open[symbol] == 100.0
    assert engine.last_tick_price[symbol] == 100.0
    assert engine.live_crossover_counts[symbol] == 0

def test_crossover_count_single_upward_cross(engine):
    """Test that a single upward crossover increments the count."""
    # Arrange
    symbol = "TEST.NSE"
    ts = int(datetime.datetime.now().timestamp())
    bar_end_ts = (ts // 60 + 1) * 60 # Timestamp for the end of the current minute
    
    # First tick sets the open price
    engine.on_message(create_tick_message(symbol, 100.0, ts))
    assert engine.live_crossover_counts[symbol] == 0

    # Second tick is below open
    engine.on_message(create_tick_message(symbol, 99.0, ts + 1))
    assert engine.live_crossover_counts[symbol] == 0

    # Third tick crosses above open
    engine.on_message(create_tick_message(symbol, 101.0, ts + 2))

    # Assert
    assert engine.live_crossover_counts[symbol] == 1

    # Now, complete the bar and check if the count is passed to the strategy and reset
    engine.on_message(create_tick_message(symbol, 101.5, bar_end_ts + 1))
    engine.strategies[0].on_data.assert_called_with(ANY, ANY, is_live_trading=True, live_crossover_count=1)
    assert engine.live_crossover_counts[symbol] == 0 # Should reset after bar completion

def test_crossover_count_multiple_crosses(engine):
    """Test that multiple crossovers are counted correctly."""
    # Arrange
    symbol = "TEST.NSE"
    ts = int(datetime.datetime.now().timestamp())
    
    engine.on_message(create_tick_message(symbol, 100.0, ts)) # Open = 100
    
    # First crossover
    engine.on_message(create_tick_message(symbol, 99.0, ts + 1))
    engine.on_message(create_tick_message(symbol, 101.0, ts + 2))
    assert engine.live_crossover_counts[symbol] == 1

    # Go back below
    engine.on_message(create_tick_message(symbol, 98.0, ts + 3))
    assert engine.live_crossover_counts[symbol] == 1

    # Second crossover (exactly at open price)
    engine.on_message(create_tick_message(symbol, 100.0, ts + 4))
    assert engine.live_crossover_counts[symbol] == 2

def test_crossover_count_no_cross(engine):
    """Test that the count remains zero if price never crosses."""
    # Arrange
    symbol = "TEST.NSE"
    ts = int(datetime.datetime.now().timestamp())
    
    engine.on_message(create_tick_message(symbol, 100.0, ts)) # Open = 100
    
    # Ticks that stay above open
    engine.on_message(create_tick_message(symbol, 101.0, ts + 1))
    engine.on_message(create_tick_message(symbol, 102.0, ts + 2))
    
    # Assert
    assert engine.live_crossover_counts[symbol] == 0

def test_crossover_count_multi_symbol(engine):
    """Test that crossover counts are tracked independently for multiple symbols."""
    # Arrange
    symbol1 = "RELIANCE.NSE"
    symbol2 = "SBIN.NSE"
    ts = int(datetime.datetime.now().timestamp())

    # Act
    engine.on_message(create_tick_message(symbol1, 2800.0, ts))
    engine.on_message(create_tick_message(symbol2, 600.0, ts))
    engine.on_message(create_tick_message(symbol1, 2799.0, ts + 1))
    engine.on_message(create_tick_message(symbol1, 2801.0, ts + 2))
    engine.on_message(create_tick_message(symbol2, 601.0, ts + 3))

    # Assert
    assert engine.live_crossover_counts[symbol1] == 1
    assert engine.live_crossover_counts[symbol2] == 0