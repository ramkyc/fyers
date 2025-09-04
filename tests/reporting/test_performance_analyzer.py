# tests/reporting/test_performance_analyzer.py

import pytest
import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.paper_trading.portfolio import Portfolio
from src.reporting.performance_analyzer import PerformanceAnalyzer

@pytest.fixture
def populated_portfolio():
    portfolio = Portfolio(initial_cash=100000.0)
    timestamp = datetime.datetime(2025, 1, 1, 9, 15, 0)

    # Simulate some trades
    # Trade 1: Buy SBIN, then sell for profit
    portfolio.execute_order("NSE:SBIN-EQ", 'BUY', 10, 500.0, timestamp)
    portfolio.execute_order("NSE:SBIN-EQ", 'SELL', 10, 510.0, timestamp + datetime.timedelta(minutes=10))

    # Trade 2: Buy RELIANCE, still open, unrealized loss
    portfolio.execute_order("NSE:RELIANCE-EQ", 'BUY', 5, 2500.0, timestamp + datetime.timedelta(minutes=20))

    # Trade 3: Buy HDFCBANK, still open, unrealized profit
    portfolio.execute_order("NSE:HDFCBANK-EQ", 'BUY', 20, 1500.0, timestamp + datetime.timedelta(minutes=30))

    return portfolio

def test_calculate_metrics(populated_portfolio):
    # Define final prices for open positions
    final_prices = {
        "NSE:RELIANCE-EQ": 2450.0, # Unrealized loss of 50 * 5 = 250
        "NSE:HDFCBANK-EQ": 1520.0  # Unrealized profit of 20 * 20 = 400
    }

    analyzer = PerformanceAnalyzer(populated_portfolio)
    metrics = analyzer.calculate_metrics(final_prices)

    # Expected values
    expected_initial_cash = 100000.0
    # Cash after SBIN trades: 100000 - (10*500) + (10*510) = 100000 - 5000 + 5100 = 100100
    # Cash after RELIANCE buy: 100100 - (5*2500) = 100100 - 12500 = 87600
    # Cash after HDFCBANK buy: 87600 - (20*1500) = 87600 - 30000 = 57600
    expected_final_cash = 57600.0

    # Holdings value: (5 * 2450) + (20 * 1520) = 12250 + 30400 = 42650
    expected_holdings_value = 42650.0

    # Total portfolio value: 57600 + 42650 = 100250
    expected_total_portfolio_value = 100250.0

    # Total P&L: 100250 - 100000 = 250
    expected_total_pnl = 250.0

    # Realized P&L (from SBIN): (510-500)*10 = 100
    expected_realized_pnl = 100.0

    # Unrealized P&L: (-250 from RELIANCE) + (400 from HDFCBANK) = 150
    expected_unrealized_pnl = 150.0

    # Assertions
    assert metrics['initial_cash'] == expected_initial_cash
    assert metrics['final_cash'] == expected_final_cash
    assert metrics['holdings_value'] == expected_holdings_value
    assert metrics['total_portfolio_value'] == expected_total_portfolio_value
    assert metrics['total_pnl'] == expected_total_pnl
    assert metrics['realized_pnl'] == expected_realized_pnl
    assert metrics['unrealized_pnl'] == expected_unrealized_pnl
    assert metrics['total_trades'] == 4

    # Test win/loss counts (corrected expectations)
    assert metrics['winning_trades'] == 1
    assert metrics['losing_trades'] == 0
    assert metrics['win_rate'] == 1.0
    assert metrics['average_win'] == 100.0 # Corrected to realized P&L of winning trade
    assert metrics['average_loss'] == 0.0
    assert metrics['profit_factor'] == float('inf') # Corrected, as total_realized_loss is 0
