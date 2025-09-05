# src/paper_trading/portfolio.py

import datetime
import config # config.py is now in the project root

class Portfolio:
    """
    Manages the state of a paper trading account, including cash, positions, and P&L.
    This class is designed to be used by both the backtesting and live paper trading engines.
    """
    def __init__(self, initial_cash=100000.0, enable_logging=True):
        """
        Initializes the portfolio.

        Args:
            initial_cash (float): The starting cash balance.
            enable_logging (bool): Whether to log portfolio performance to the database.
        """
        self.initial_cash = initial_cash
        self.current_cash = initial_cash
        self.positions = {}  # Key: symbol, Value: {'quantity': int, 'avg_price': float}
        self.trades = [] # To log all trades
        self.equity_curve = [] # To log portfolio value over time for backtest analysis
        self.enable_logging = enable_logging

    def log_portfolio_value(self, timestamp, current_prices):
        """
        Logs the portfolio's value. For backtesting, it stores in memory.
        For live trading, the engine itself handles DB logging.
        """
        summary = self.get_performance_summary(current_prices)
        
        # Always append to the in-memory list for backtest analysis
        self.equity_curve.append(
            {'timestamp': timestamp, 
             'value': summary['total_portfolio_value'],
             'cash': summary['final_cash'],
             'holdings': summary['holdings_value']
            }
        )

    def execute_order(self, symbol: str, action: str, quantity: int, price: float, timestamp: datetime):
        """
        Executes a trade and updates the portfolio state.
        This is the primary interface for strategies to interact with the portfolio.

        Args:
            symbol (str): The stock symbol.
            action (str): The trade action ('BUY' or 'SELL').
            quantity (int): The number of shares.
            price (float): The price at which the trade was executed.
            timestamp (datetime): The timestamp of the trade from the data.
        """
        if action == 'BUY':
            self._update_position(symbol, quantity, price, timestamp, action)
        elif action == 'SELL':
            current_position = self.get_position(symbol)
            if current_position and current_position['quantity'] >= quantity:
                self._update_position(symbol, -quantity, price, timestamp, action)
            else:
                print(f"{timestamp} | REJECTED SELL: Insufficient long position for {symbol}. Attempted to sell {quantity}, but held {current_position['quantity'] if current_position else 0}.")
        else:
            print(f"Warning: Unknown action '{action}' provided to execute_order.")

    def _update_position(self, symbol, quantity, price, timestamp, action):
        """
        Internal method to update a position after a trade.
        """
        trade_value = abs(quantity) * price
        # Decrease cash for buy (positive quantity), increase for sell (negative quantity)
        self.current_cash -= (quantity * price)

        # Log the trade
        self.trades.append({
            'timestamp': timestamp,
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'action': action
        })

        # Update holdings
        if symbol not in self.positions:
            self.positions[symbol] = {'quantity': 0, 'avg_price': 0.0}

        current_quantity = self.positions[symbol]['quantity']
        current_avg_price = self.positions[symbol]['avg_price']

        new_quantity = current_quantity + quantity

        if new_quantity == 0:
            # Position is closed
            del self.positions[symbol]
        else:
            # Update average price for buys
            if quantity > 0:
                new_avg_price = ((current_avg_price * current_quantity) + (price * quantity)) / new_quantity
                self.positions[symbol]['avg_price'] = new_avg_price

            self.positions[symbol]['quantity'] = new_quantity

        print(f"{timestamp} | Trade: {'BUY' if quantity > 0 else 'SELL'} {abs(quantity)} {symbol} @ {price:.2f}")

    def get_position(self, symbol: str):
        """
        Retrieves the current position for a given symbol.

        Args:
            symbol (str): The stock symbol.

        Returns:
            dict or None: The position dictionary or None if no position exists.
        """
        return self.positions.get(symbol)

    def get_performance_summary(self, current_prices):
        """
        Calculates a detailed performance summary of the portfolio.

        Args:
            current_prices (dict): A dictionary mapping symbols to their last known price.

        Returns:
            dict: A dictionary containing key performance indicators.
        """
        holdings_value = 0.0
        unrealized_pnl = 0.0
        
        for symbol, data in self.positions.items():
            current_price = current_prices.get(symbol, data['avg_price'])
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

    def print_final_summary(self, current_prices):
        """
        Prints a detailed final summary of the portfolio's performance.

        Args:
            current_prices (dict): A dictionary mapping symbols to their last known price.
        """
        summary = self.get_performance_summary(current_prices)

        print("\n--- Final Performance Summary ---")
        print(f"Starting Portfolio Value: {summary['initial_cash']:,.2f}")
        print(f"Ending Portfolio Value:   {summary['total_portfolio_value']:,.2f}")
        print("-----------------------------")
        print(f"Total P&L:                {summary['total_pnl']:,.2f}")
        print(f"  - Realized P&L:         {summary['realized_pnl']:,.2f}")
        print(f"  - Unrealized P&L:       {summary['unrealized_pnl']:,.2f}")
        print("-----------------------------")
        print(f"Final Cash Balance:       {summary['final_cash']:,.2f}")
        print(f"Final Holdings Value:     {summary['holdings_value']:,.2f}")
        
        print("\n--- Open Positions at End of Backtest ---")
        if not self.positions:
            print("  <No open positions>")
        else:
            for symbol, data in self.positions.items():
                last_price = current_prices.get(symbol, data['avg_price'])
                market_value = data['quantity'] * last_price
                pnl = market_value - (data['quantity'] * data['avg_price'])
                print(f"  - {symbol}: {data['quantity']} shares @ avg {data['avg_price']:.2f} | Mkt Value: {market_value:,.2f} | P&L: {pnl:,.2f}")

        print("\n--- Trade Log ---")
        if not self.trades:
            print("  <No trades executed>")
        else:
            sorted_trades = sorted(self.trades, key=lambda x: x['timestamp'])
            print(f"  Total Trades: {len(sorted_trades)}")
            for trade in sorted_trades:
                print(f"  - {trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}: {trade['action']} {abs(trade['quantity'])} {trade['symbol']} @ {trade['price']:.2f}")
        
        print("---------------------------------")
