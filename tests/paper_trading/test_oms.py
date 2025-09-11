# tests/paper_trading/test_oms.py

import pytest
from unittest.mock import MagicMock, patch
import datetime

from paper_trading.oms import OrderManager
from paper_trading.portfolio import Portfolio
from symbol_manager import SymbolManager

# --- Mocks and Fixtures ---

@pytest.fixture
def mock_portfolio():
    """Provides a mock Portfolio instance."""
    portfolio = MagicMock(spec=Portfolio)
    # Mock the get_position method to control its return value in tests
    portfolio.get_position.return_value = None
    return portfolio

@pytest.fixture
def mock_symbol_manager():
    """Provides a mock SymbolManager instance with pre-defined lot sizes."""
    with patch('symbol_manager.SymbolManager._load_master_data', return_value=None):
        manager = SymbolManager()
        # Manually set the lot sizes for testing
        manager._lot_sizes = {
            "NSE:SBIN-EQ": 1,
            "NSE:NIFTY25SEP25000CE": 50
        }
        return manager

@pytest.fixture
def oms(mock_portfolio, mock_symbol_manager):
    """Provides an OrderManager instance with mocked dependencies."""
    # Patch the SymbolManager singleton to return our mock instance. The path is now relative to src.
    with patch('paper_trading.oms.SymbolManager', return_value=mock_symbol_manager):
        order_manager = OrderManager(portfolio=mock_portfolio, run_id="test_run")
        return order_manager

# --- Test Cases ---

def test_execute_buy_order_stock(oms, mock_portfolio):
    """Test that a simple stock buy order is executed correctly."""
    # Arrange
    signal = {
        'symbol': 'NSE:SBIN-EQ', 'timeframe': 'D', 'action': 'BUY',
        'quantity': 10, 'price': 600.0, 'timestamp': datetime.datetime.now()
    }

    # Act
    oms.execute_order(signal, is_live_trading=False)

    # Assert
    # Check that the portfolio's execute_order was called with the correct, unadjusted quantity
    mock_portfolio.execute_order.assert_called_once_with(
        'NSE:SBIN-EQ', 'D', 'BUY', 10, 600.0, signal['timestamp']
    )

def test_execute_buy_order_options_lot_size_adjustment(oms, mock_portfolio):
    """Test that an option order quantity is rounded down to the nearest lot size."""
    # Arrange
    signal = {
        'symbol': 'NSE:NIFTY25SEP25000CE', 'timeframe': '15', 'action': 'BUY',
        'quantity': 120, 'price': 150.0, 'timestamp': datetime.datetime.now()
    } # 120 is not a multiple of 50

    # Act
    oms.execute_order(signal, is_live_trading=False)

    # Assert
    # The quantity should be adjusted from 120 down to 100 (2 lots of 50)
    mock_portfolio.execute_order.assert_called_once_with(
        'NSE:NIFTY25SEP25000CE', '15', 'BUY', 100, 150.0, signal['timestamp']
    )

def test_reject_sell_order_with_no_position(oms, mock_portfolio):
    """Test that a SELL order is rejected if there is no open long position."""
    # Arrange
    # The mock_portfolio is configured by default to return None for get_position
    signal = {
        'symbol': 'NSE:SBIN-EQ', 'timeframe': 'D', 'action': 'SELL',
        'quantity': 10, 'price': 610.0, 'timestamp': datetime.datetime.now()
    }

    # Act
    oms.execute_order(signal, is_live_trading=False)

    # Assert
    # The portfolio's execute_order should NOT be called
    mock_portfolio.execute_order.assert_not_called()