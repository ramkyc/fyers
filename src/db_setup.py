# src/db_setup.py

import sqlite3
import os
import sys

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def setup_databases():
    """
    Initializes all SQLite databases and creates the necessary tables
    if they do not already exist. This script is safe to run multiple times.
    """
    print("--- Starting Database Setup ---")

    # Ensure the data directory exists
    if not os.path.exists(config.DATA_DIR):
        os.makedirs(config.DATA_DIR)
        print(f"Created data directory at: {config.DATA_DIR}")

    # --- 1. Setup Historical Market Data Database ---
    try:
        with sqlite3.connect(config.HISTORICAL_MARKET_DB_FILE) as con:
            print(f"Connected to historical market database: {config.HISTORICAL_MARKET_DB_FILE}")
            cursor = con.cursor()
            # Table for historical OHLCV candle data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_data (
                    timestamp TIMESTAMP,
                    symbol TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    resolution TEXT,
                    UNIQUE(timestamp, symbol, resolution)
                );
            """)
            print("  - Table 'historical_data' is ready.")
            # Table for archived live tick data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_ticks (
                    timestamp TIMESTAMP,
                    symbol TEXT,
                    ltp REAL,
                    volume INTEGER,
                    UNIQUE(timestamp, symbol)
                );
            """)
            print("  - Table 'historical_ticks' is ready.")
    except Exception as e:
        print(f"ERROR setting up historical market database: {e}")

    # --- 2. Setup Live Market Data Database ---
    try:
        with sqlite3.connect(config.LIVE_MARKET_DB_FILE) as con:
            print(f"Connected to live market database: {config.LIVE_MARKET_DB_FILE}")
            cursor = con.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_ticks (
                    timestamp TIMESTAMP,
                    symbol TEXT,
                    ltp REAL,
                    volume INTEGER,
                    UNIQUE(timestamp, symbol)
                );
            """)
            print("  - Table 'live_ticks' is ready.")
    except Exception as e:
        print(f"ERROR setting up live market database: {e}")

    # --- 3. Setup Trading Log Database ---
    try:
        with sqlite3.connect(config.TRADING_DB_FILE) as con:
            print(f"Connected to trading log database: {config.TRADING_DB_FILE}")
            cursor = con.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    timestamp TIMESTAMP, symbol TEXT, action TEXT,
                    quantity INTEGER, price REAL, is_live BOOLEAN
                );
            """)
            print("  - Table 'paper_trades' is ready.")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_log (
                    timestamp TIMESTAMP, total_portfolio_value REAL, cash REAL,
                    holdings_value REAL, realized_pnl REAL, unrealized_pnl REAL
                );
            """)
            print("  - Table 'portfolio_log' is ready.")
    except Exception as e:
        print(f"ERROR setting up trading log database: {e}")

    print("\n--- Database Setup Complete ---")

if __name__ == "__main__":
    setup_databases()