# src/db_setup.py

import sqlite3
import os
import sys

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def setup_trading_database():
    """
    Initializes the trading database and creates all necessary tables.
    This function is idempotent and can be run multiple times safely.
    """
    print(f"Setting up trading database at: {config.TRADING_DB_FILE}")
    
    # Ensure the data directory exists
    os.makedirs(config.DATA_DIR, exist_ok=True)

    with sqlite3.connect(database=config.TRADING_DB_FILE) as con:
        # Create the paper_trades table (used by OrderManager)
        con.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                timestamp TIMESTAMP,
                symbol VARCHAR,
                action VARCHAR,
                quantity BIGINT,
                price DOUBLE,
                is_live BOOLEAN
            );
        """)
        # Create the portfolio_log table (used by Portfolio)
        con.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_log (
                timestamp TIMESTAMP,
                total_portfolio_value DOUBLE,
                cash DOUBLE,
                holdings_value DOUBLE,
                realized_pnl DOUBLE,
                unrealized_pnl DOUBLE
            );
        """)
    print("Trading database setup complete. All tables are ready.")

if __name__ == "__main__":
    setup_trading_database()
