# tests/paper_trading/test_portfolio.py

import pytest
import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.paper_trading.portfolio import Portfolio

@pytest.fixture
def empty_portfolio():
    """Returns a Portfolio instance with default initial cash."""
    return Portfolio(initial_cash=100000.0)

def test_portfolio_initialization(empty_portfolio):
    """Test that the portfolio initializes with the correct cash balance."""
    assert empty_portfolio.initial_cash == 100000.0
    assert empty_portfolio.current_cash == 100000.0
    assert not empty_portfolio.positions
    assert not empty_portfolio.trades

def test_buy_order(empty_portfolio):
    """Test a single buy order and its effect on cash and positions."""
    symbol = "NSE:SBIN-EQ"
    quantity = 10
    price = 500.0
    timestamp = datetime.datetime.now()

    empty_portfolio.execute_order(symbol, 'BUY', quantity, price, timestamp)

    # Check cash deduction
    assert empty_portfolio.current_cash == 100000.0 - (quantity * price)

    # Check position
    position = empty_portfolio.get_position(symbol)
    assert position is not None
    assert position['quantity'] == quantity
    assert position['avg_price'] == price

    # Check trade log
    assert len(empty_portfolio.trades) == 1
    trade = empty_portfolio.trades[0]
    assert trade['symbol'] == symbol
    assert trade['action'] == 'BUY'
    assert trade['quantity'] == quantity
    assert trade['price'] == price

def test_sell_to_close_order(empty_portfolio):
    """
    Test selling to close an existing position.
    This test also implicitly checks realized P&L calculation.
    """
    symbol = "NSE:RELIANCE-EQ"
    buy_quantity = 20
    buy_price = 2500.0
    buy_timestamp = datetime.datetime.now()

    # First, buy shares
    empty_portfolio.execute_order(symbol, 'BUY', buy_quantity, buy_price, buy_timestamp)
    
    # Now, sell them
    sell_quantity = 20
    sell_price = 2600.0
    sell_timestamp = datetime.datetime.now() + datetime.timedelta(days=1)
    empty_portfolio.execute_order(symbol, 'SELL', sell_quantity, sell_price, sell_timestamp)

    # Check cash balance after closing position
    # Initial cash - (buy_quantity * buy_price) + (sell_quantity * sell_price)
    expected_cash = 100000.0 - (buy_quantity * buy_price) + (sell_quantity * sell_price)
    assert empty_portfolio.current_cash == expected_cash

    # Check position is closed
    assert empty_portfolio.get_position(symbol) is None

    # Check trade log
    assert len(empty_portfolio.trades) == 2

def test_partial_sell_order(empty_portfolio):
    """Test selling a part of an existing position."""
    symbol = "NSE:TCS-EQ"
    buy_quantity = 50
    buy_price = 3500.0
    buy_timestamp = datetime.datetime.now()

    empty_portfolio.execute_order(symbol, 'BUY', buy_quantity, buy_price, buy_timestamp)

    # Sell a portion
    sell_quantity = 30
    sell_price = 3600.0
    sell_timestamp = datetime.datetime.now() + datetime.timedelta(days=1)
    empty_portfolio.execute_order(symbol, 'SELL', sell_quantity, sell_price, sell_timestamp)

    # Check cash deduction
    expected_cash_after_partial_sell = 100000.0 - (buy_quantity * buy_price) + (sell_quantity * sell_price)
    assert empty_portfolio.current_cash == expected_cash_after_partial_sell

    # Check position
    position = empty_portfolio.get_position(symbol)
    assert position is not None
    assert position['quantity'] == buy_quantity - sell_quantity # 20
    assert position['avg_price'] == buy_price # Avg price doesn't change on sell

    # Check trade log
    assert len(empty_portfolio.trades) == 2

def test_get_performance_summary(empty_portfolio):
    """Test the get_performance_summary method."""
    symbol = "NSE:INFY-EQ"
    buy_quantity = 10
    buy_price = 1500.0
    buy_timestamp = datetime.datetime.now()

    empty_portfolio.execute_order(symbol, 'BUY', buy_quantity, buy_price, buy_timestamp)

    current_prices = {symbol: 1550.0} # Price increased
    summary = empty_portfolio.get_performance_summary(current_prices)

    assert summary['initial_cash'] == 100000.0
    assert summary['final_cash'] == 100000.0 - (buy_quantity * buy_price)
    assert summary['holdings_value'] == buy_quantity * current_prices[symbol]
    assert summary['total_portfolio_value'] == summary['final_cash'] + summary['holdings_value']
    assert summary['unrealized_pnl'] == (current_prices[symbol] - buy_price) * buy_quantity
    assert summary['total_pnl'] == summary['total_portfolio_value'] - summary['initial_cash']
    assert summary['realized_pnl'] == summary['total_pnl'] - summary['unrealized_pnl']
    assert summary['total_trades'] == 1
