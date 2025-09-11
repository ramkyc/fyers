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

            # Table for symbol master data (lot sizes, etc.)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbol_master (
                    symbol_ticker TEXT,
                    symbol_details TEXT,
                    lot_size INTEGER,
                    instrument_type TEXT,
                    underlying_id TEXT,
                    strike_price REAL,
                    option_type TEXT,
                    expiry_date TEXT
                );
            """)
            print("  - Table 'symbol_master' is ready.")
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

            # Table for pre-populating strategy data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_strategy_data (
                    timestamp TIMESTAMP, symbol TEXT, resolution TEXT,
                    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
                    UNIQUE(symbol, resolution, timestamp)
                );
            """)
            print("  - Table 'live_strategy_data' is ready.")

            # Table for the live, forming candle for the UI
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_incomplete_bars (
                    symbol TEXT PRIMARY KEY, timestamp TIMESTAMP, open REAL, high REAL, low REAL, close REAL, volume REAL
                );
            """)
            print("  - Table 'live_incomplete_bars' is ready.")
    except Exception as e:
        print(f"ERROR setting up live market database: {e}")

    # --- 3. Setup Trading Log Database ---
    try:
        with sqlite3.connect(config.TRADING_DB_FILE) as con:
            print(f"Connected to trading log database: {config.TRADING_DB_FILE}")
            cursor = con.cursor()

            # --- Migration Logic to Add run_id if Missing ---
            def add_column_if_not_exists(table_name, column_name, column_type):
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [info[1] for info in cursor.fetchall()]
                if column_name not in columns:
                    print(f"  - Migrating '{table_name}': adding '{column_name}' column...")
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    print(f"  - Migration complete for '{table_name}'.")

            # Step 1: Create tables if they don't exist (without run_id initially for compatibility)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    timestamp TIMESTAMP, symbol TEXT, action TEXT, quantity INTEGER, price REAL, is_live BOOLEAN
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_log (
                    timestamp TIMESTAMP, total_portfolio_value REAL, cash REAL, holdings_value REAL, realized_pnl REAL, unrealized_pnl REAL
                );
            """)

            # Step 2: Run migration to add the 'run_id' column if it's missing
            add_column_if_not_exists('paper_trades', 'run_id', 'TEXT')
            add_column_if_not_exists('portfolio_log', 'run_id', 'TEXT')

            # Step 3: Now that the column is guaranteed to exist, create the index
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_run_id ON paper_trades(run_id);")
            print("  - Table 'paper_trades' is ready.")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_log_run_id ON portfolio_log(run_id);")
            print("  - Table 'portfolio_log' is ready.")

            # Table for live position tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_positions (
                    run_id TEXT,
                    timestamp TIMESTAMP,
                    symbol TEXT,
                    timeframe TEXT,
                    quantity INTEGER,
                    avg_price REAL,
                    ltp REAL,
                    mtm REAL
                );
            """)
            print("  - Table 'live_positions' is ready.")

            con.commit()

    except Exception as e:
        print(f"ERROR setting up trading log database: {e}")

    print("\n--- Database Setup Complete ---")

if __name__ == "__main__":
    setup_databases()