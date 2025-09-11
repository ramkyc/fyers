# src/reporting/performance_analyzer.py

from collections import deque
import pandas as pd
import numpy as np
from collections import defaultdict

class PerformanceAnalyzer:
    """
    Analyzes the performance of a portfolio from a backtest.
    """
    def __init__(self, portfolio):
        self.portfolio = portfolio

    def _calculate_trade_pnl(self) -> tuple[list[float], list[float]]:
        """
        Calculates the P&L for each individual round-trip trade using a FIFO approach.

        Returns:
            A tuple containing two lists: (winning_trades_pnl, losing_trades_pnl)
        """
        trades = sorted(self.portfolio.trades, key=lambda x: x['timestamp'])
        open_positions = defaultdict(lambda: deque()) # Using deque for efficient FIFO
        realized_pnl_list = []

        for trade in trades:
            symbol = trade.get('symbol')
            timeframe = trade.get('timeframe', 'D') # Default for old data
            position_key = (symbol, timeframe)
            
            if trade['action'] == 'BUY':
                # Add buy trade to the queue for that symbol
                open_positions[position_key].append({
                    'quantity': trade['quantity'],
                    'price': trade['price']
                })
            elif trade['action'] == 'SELL':
                sell_quantity = abs(trade['quantity'])
                sell_price = trade['price']
                
                while sell_quantity > 0 and open_positions[position_key]:
                    buy_trade = open_positions[position_key][0]
                    
                    # Determine the quantity to match
                    matched_quantity = min(sell_quantity, buy_trade['quantity'])
                    
                    # Calculate P&L for the matched portion
                    pnl = (sell_price - buy_trade['price']) * matched_quantity
                    realized_pnl_list.append(pnl)
                    
                    # Update quantities
                    sell_quantity -= matched_quantity
                    buy_trade['quantity'] -= matched_quantity
                    
                    # If the buy trade is fully closed, remove it from the queue
                    if buy_trade['quantity'] == 0:
                        open_positions[position_key].popleft()

                if sell_quantity > 0:
                    # This case implies a short sale which we are not currently tracking P&L for
                    # in this FIFO logic designed for closing long positions.
                    # For now, we ignore it, but a more complex system could handle it.
                    pass

        winning_trades_pnl = [pnl for pnl in realized_pnl_list if pnl > 0]
        losing_trades_pnl = [pnl for pnl in realized_pnl_list if pnl <= 0]

        return winning_trades_pnl, losing_trades_pnl

    def _calculate_max_drawdown(self) -> float:
        """
        Calculates the maximum drawdown from the portfolio's equity curve.
        """
        if not self.portfolio.equity_curve:
            return 0.0

        equity_df = pd.DataFrame(self.portfolio.equity_curve)
        equity_df['peak'] = equity_df['value'].cummax()
        equity_df['drawdown'] = (equity_df['value'] - equity_df['peak']) / equity_df['peak']
        
        max_drawdown = equity_df['drawdown'].min()
        return abs(max_drawdown)

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.06) -> float:
        """
        Calculates the annualized Sharpe Ratio.

        Args:
            risk_free_rate (float): The annual risk-free rate.

        Returns:
            float: The annualized Sharpe Ratio.
        """
        if len(self.portfolio.equity_curve) < 2:
            return 0.0

        equity_df = pd.DataFrame(self.portfolio.equity_curve)
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
        equity_df = equity_df.set_index('timestamp')

        # Resample to daily returns to standardize
        # Forward-fill to handle non-trading days (weekends, holidays) before calculating returns
        daily_series = equity_df['value'].resample('D').last().ffill()
        daily_returns = daily_series.pct_change().dropna()

        if daily_returns.empty or daily_returns.std() == 0:
            return 0.0

        # Calculate annualized excess returns
        excess_returns = daily_returns - (risk_free_rate / 252) # Daily risk-free rate
        
        # Calculate annualized Sharpe Ratio
        # (252 is the standard number of trading days in a year)
        sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)

        # If the strategy never traded or had no volatility, Sharpe can be NaN.
        if np.isnan(sharpe_ratio):
            return 0.0
            
        return sharpe_ratio


    def calculate_metrics(self, final_prices: dict) -> dict:
        """
        Calculates key performance metrics for the portfolio.

        Args:
            final_prices (dict): A dictionary of the last known prices for open positions.

        Returns:
            dict: A dictionary containing various performance metrics.
        """
        summary = self.portfolio.get_performance_summary(final_prices)
        
        # Calculate per-trade P&L
        winning_pnl, losing_pnl = self._calculate_trade_pnl()

        # Calculate advanced metrics
        max_drawdown = self._calculate_max_drawdown()
        sharpe_ratio = self._calculate_sharpe_ratio()

        metrics = {
            "initial_cash": summary['initial_cash'],
            "final_cash": summary['final_cash'],
            "holdings_value": summary['holdings_value'],
            "total_portfolio_value": summary['total_portfolio_value'],
            "total_pnl": summary['total_pnl'],
            "realized_pnl": summary['realized_pnl'],
            "unrealized_pnl": summary['unrealized_pnl'],
            "total_trades": summary['total_trades'],
            "winning_trades": len(winning_pnl),
            "losing_trades": len(losing_pnl),
            "win_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "total_realized_pnl_from_trades": sum(winning_pnl) + sum(losing_pnl)
        }

        total_wins = sum(winning_pnl)
        total_losses = abs(sum(losing_pnl))

        if metrics['winning_trades'] + metrics['losing_trades'] > 0:
            metrics['win_rate'] = metrics['winning_trades'] / (metrics['winning_trades'] + metrics['losing_trades'])
        
        if metrics['winning_trades'] > 0:
            metrics['average_win'] = total_wins / metrics['winning_trades']
        if metrics['losing_trades'] > 0:
            metrics['average_loss'] = -total_losses / metrics['losing_trades']

        if total_losses > 0:
            metrics['profit_factor'] = total_wins / total_losses
        elif total_wins > 0:
            metrics['profit_factor'] = float('inf')

        return metrics

    def print_performance_report(self, final_prices: dict, run_id: str = "N/A"):
        """
        Prints a detailed performance report.
        """
        metrics = self.calculate_metrics(final_prices)

        print("\n--- Backtest Performance Report ---")
        print(f"Run ID: {run_id}")
        print(f"Initial Portfolio Value: {metrics['initial_cash']:,.2f}")
        print(f"Final Portfolio Value:   {metrics['total_portfolio_value']:,.2f}")
        print("-----------------------------------")
        print(f"Total P&L:               {metrics['total_pnl']:,.2f}")
        print(f"  - Realized P&L:        {metrics['realized_pnl']:,.2f}")
        print(f"  - Unrealized P&L:      {metrics['unrealized_pnl']:,.2f}")
        print(f"-----------------------------------")
        print(f"Total Trades:            {metrics['total_trades']}")
        print(f"Winning Trades:          {metrics['winning_trades']}")
        print(f"Losing Trades:           {metrics['losing_trades']}")
        print(f"Win Rate:                {metrics['win_rate']:.2%}")
        print(f"Average Win:             {metrics['average_win']:,.2f}")
        print(f"Average Loss:            {metrics['average_loss']:,.2f}")
        print(f"Profit Factor:           {metrics['profit_factor']:.2f}")
        print("-----------------------------------")
        print(f"Max Drawdown:            {metrics['max_drawdown']:.2%}")
        print(f"Sharpe Ratio:            {metrics['sharpe_ratio']:.2f}")
        print("-----------------------------------")

        print("\n--- Open Positions at End of Backtest ---")
        if not self.portfolio.positions:
            print("  <No open positions>")
        else:
            for (symbol, timeframe), data in self.portfolio.positions.items():
                last_price = final_prices.get(symbol, data['avg_price'])
                market_value = data['quantity'] * last_price
                pnl = market_value - (data['quantity'] * data['avg_price'])
                print(f"  - {symbol} ({timeframe}): {data['quantity']} shares @ avg {data['avg_price']:.2f} | Mkt Value: {market_value:,.2f} | P&L: {pnl:,.2f}")

        print("\n--- Trade Log ---")
        if not self.portfolio.trades:
            print("  <No trades executed>")
        else:
            sorted_trades = sorted(self.portfolio.trades, key=lambda x: x['timestamp'])
            print(f"  Total Trades: {len(sorted_trades)}")
            for trade in sorted_trades:
                print(f"  - {trade['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}: {trade['action']} {abs(trade['quantity'])} {trade['symbol']} @ {trade['price']:.2f}")
        
        print("-----------------------------------")