# src/db_setup.py

import sqlite3
import os
import sys

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def add_column_if_not_exists(con, cursor, table_name, column_name, column_type):
    """A helper function to add a column to a table if it doesn't already exist."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [info[1] for info in cursor.fetchall()]
    if column_name not in columns:
        print(f"  - Migrating '{table_name}': adding '{column_name}' column...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        con.commit() # Commit the change immediately
        print(f"  - Migration complete for '{table_name}'.")

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
                    fy_token TEXT,
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
            # Add migration for fy_token if it doesn't exist
            add_column_if_not_exists(con, cursor, 'symbol_master', 'fy_token', 'TEXT')
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

            # --- Trade Log Table Refactoring ---
            # Rename the old 'paper_trades' table to 'live_paper_trades' if it exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'")
            if cursor.fetchone():
                try:
                    cursor.execute("ALTER TABLE paper_trades RENAME TO live_paper_trades")
                    print("  - Renamed 'paper_trades' to 'live_paper_trades'.")
                except sqlite3.OperationalError:
                    # This can happen if the table is somehow in use. We'll proceed assuming it's okay.
                    pass

            # Create the new, separated trade log tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_paper_trades (
                    run_id TEXT, timestamp TIMESTAMP, symbol TEXT, timeframe TEXT, action TEXT, quantity INTEGER, price REAL
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backtest_trades (
                    run_id TEXT, timestamp TIMESTAMP, symbol TEXT, timeframe TEXT, action TEXT, quantity INTEGER, price REAL
                );
            """)

            # Run migrations on the new tables to ensure they have the correct columns
            add_column_if_not_exists(con, cursor, 'live_paper_trades', 'run_id', 'TEXT')
            add_column_if_not_exists(con, cursor, 'live_paper_trades', 'timeframe', 'TEXT')
            add_column_if_not_exists(con, cursor, 'backtest_trades', 'run_id', 'TEXT')
            add_column_if_not_exists(con, cursor, 'backtest_trades', 'timeframe', 'TEXT')

            # Step 3: Now that the column is guaranteed to exist, create the index
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_live_paper_trades_run_id ON live_paper_trades(run_id);")
            print("  - Table 'live_paper_trades' is ready.")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(run_id);")
            print("  - Table 'backtest_trades' is ready.")

            # Table for live position tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_positions (
                    run_id TEXT,
                    timestamp TIMESTAMP,
                    symbol TEXT,
                    timeframe TEXT,
                    quantity INTEGER, avg_price REAL, ltp REAL, mtm REAL,
                    stop_loss REAL,
                    target1 REAL,
                    target2 REAL,
                    target3 REAL,
                    PRIMARY KEY (run_id, symbol, timeframe)
                ) WITHOUT ROWID;
            """)
            print("  - Table 'live_positions' is ready.")

            # Table for structured live debug logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pt_live_debug_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
                    timestamp TIMESTAMP,
                    log_data TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pt_live_debug_log_run_id ON pt_live_debug_log(run_id);")
            print("  - Table 'pt_live_debug_log' is ready.")

            # New separated tables for storing detailed equity curve data
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pt_portfolio_log (
                    run_id TEXT, timestamp TIMESTAMP, value REAL, cash REAL, holdings REAL, pnl REAL
                );
            """)
            print("  - Table 'pt_portfolio_log' is ready.")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bt_portfolio_log (
                    run_id TEXT,
                    timestamp TIMESTAMP,
                    value REAL,
                    cash REAL,
                    holdings REAL,
                    pnl REAL
                );
            """)
            print("  - Table 'bt_portfolio_log' is ready.")
            con.commit()

    except Exception as e:
        print(f"ERROR setting up trading log database: {e}")

    print("\n--- Database Setup Complete ---")

if __name__ == "__main__":
    setup_databases()