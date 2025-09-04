import datetime
from src.paper_trading.portfolio import Portfolio

portfolio = Portfolio(initial_cash=100000.0)
current_prices = {"MOCK:STOCK": 100.0}

# Simulate 105 trades to trigger logging
for i in range(105):
    symbol = "MOCK:STOCK"
    quantity = 1
    price = 100.0 + i % 10  # Vary price a bit
    timestamp = datetime.datetime.now() + datetime.timedelta(seconds=i)
    portfolio._update_position(symbol, quantity, price, timestamp, current_prices)

print("Simulated trades complete. Check DuckDB 'portfolio_log' table for entries.")
