# src/backtesting/bt_portfolio.py

import datetime
import config

class BT_Portfolio:
    """
    Manages the state of a portfolio during a backtest.
    This is a simplified, in-memory version designed for speed and isolation.
    Each backtest run will have its own instance of this class.
    """
    def __init__(self, initial_cash=100000.0, run_id: str = None):
        """
        Initializes the backtest portfolio.

        Args:
            initial_cash (float): The starting cash balance.
            run_id (str): A unique identifier for this backtest run.
        """
        self.run_id = run_id
        self.initial_cash = initial_cash
        self.current_cash = initial_cash
        self.positions = {}  # Key: (symbol, timeframe), Value: {'quantity': int, 'avg_price': float}
        self.trades = [] # To log all trades for this run
        self.position_capital = {} # Key: (symbol, timeframe), Value: float (compounding capital for this slot)
        self.equity_curve = [] # To log portfolio value over time for this run

    def log_portfolio_value(self, timestamp, current_prices):
        """
        Logs the portfolio's value to the in-memory equity curve.
        """
        summary = self.get_performance_summary(current_prices)
        
        self.equity_curve.append(
            {'timestamp': timestamp, 
             'value': summary['total_portfolio_value'],
             'cash': summary['final_cash'],
             'holdings': summary['holdings_value']
            }
        )

    def execute_order(self, symbol: str, timeframe: str, action: str, quantity: int, price: float, timestamp: datetime):
        """
        Executes a simulated trade and updates the portfolio state.
        """
        if action == 'BUY':
            self._update_position(symbol, timeframe, quantity, price, timestamp, action)
        elif action == 'SELL':
            current_position = self.get_position(symbol, timeframe)
            if current_position and current_position['quantity'] >= quantity:
                self._update_position(symbol, timeframe, -quantity, price, timestamp, action)
            else:
                # In a backtest, this is just a log message, not a hard rejection
                print(f"{timestamp} | INFO: Cannot SELL {symbol}, no open position.")

    def _update_position(self, symbol, timeframe, quantity, price, timestamp, action):
        """
        Internal method to update a position after a trade.
        """
        position_key = (symbol, timeframe)

        # On a sell, calculate realized P&L and add it back to the position's capital
        if quantity < 0: # This is a sell trade
            realized_pnl = (price - self.positions[position_key]['avg_price']) * abs(quantity)
            self.position_capital[position_key] += realized_pnl

        self.current_cash -= (quantity * price)

        self.trades.append({
            'timestamp': timestamp,
            'symbol': symbol,
            'timeframe': timeframe,
            'quantity': quantity,
            'price': price,
            'action': action,
            'run_id': self.run_id
        })

        if position_key not in self.positions:
            self.positions[position_key] = {'quantity': 0, 'avg_price': 0.0}

        current_quantity = self.positions[position_key]['quantity']
        current_avg_price = self.positions[position_key]['avg_price']
        new_quantity = current_quantity + quantity

        if new_quantity == 0:
            del self.positions[position_key]
        else:
            if quantity > 0: # Update average price only on buys
                new_avg_price = ((current_avg_price * current_quantity) + (price * quantity)) / new_quantity
                self.positions[position_key]['avg_price'] = new_avg_price
            self.positions[position_key]['quantity'] = new_quantity

    def get_position(self, symbol: str, timeframe: str):
        """
        Retrieves the current position for a given symbol and timeframe.
        """
        return self.positions.get((symbol, timeframe))

    def get_capital_for_position(self, symbol: str, timeframe: str, default_trade_value: float) -> float:
        """
        Gets the available, compounding capital for a specific position slot.
        """
        position_key = (symbol, timeframe)
        if position_key not in self.position_capital:
            self.position_capital[position_key] = default_trade_value
        return self.position_capital[position_key]

    def get_performance_summary(self, current_prices):
        """
        Calculates a detailed performance summary of the portfolio.
        """
        holdings_value = 0.0
        unrealized_pnl = 0.0
        
        for (symbol, timeframe), data in self.positions.items():
            # Use the current price if available, otherwise fall back to the position's average price.
            # This prevents errors if a tick is missing for a symbol we hold.
            current_price = current_prices.get(symbol) or data['avg_price']

            market_value = data['quantity'] * current_price
            holdings_value += market_value
            unrealized_pnl += market_value - (data['quantity'] * data['avg_price'])

        total_portfolio_value = self.current_cash + holdings_value
        total_pnl = total_portfolio_value - self.initial_cash
        realized_pnl = total_pnl - unrealized_pnl

        return {
            "initial_cash": self.initial_cash,
            "final_cash": self.current_cash,
            "holdings_value": holdings_value,
            "total_portfolio_value": total_portfolio_value,
            "total_pnl": total_pnl,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_trades": len(self.trades)
        }