# scripts/clear_trading_logs.py

import os
import sys

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config
import sqlite3

def clear_database_tables(db_path, tables_to_clear):
    """
    A generic function to clear all records from specified tables in a given database.
    """
    if not os.path.exists(db_path):
        print(f"Database file not found at '{db_path}'. Nothing to clear.")
        return

    print(f"\nConnecting to '{os.path.basename(db_path)}' to clear tables...")
    try:
        with sqlite3.connect(db_path, timeout=10) as con:
            cursor = con.cursor()
            for table in tables_to_clear:
                # Check if table exists before trying to delete from it
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                if cursor.fetchone():
                    cursor.execute(f"DELETE FROM {table};")
                    print(f"  - Cleared all records from '{table}'.")
                else:
                    print(f"  - Table '{table}' not found, skipping.")
            con.commit()
        print(f"✅ Successfully cleared tables in '{os.path.basename(db_path)}'.")
    except Exception as e:
        print(f"❌ ERROR: An error occurred during cleanup for '{db_path}': {e}")

def clear_logs():
    """
    Connects to all relevant databases and clears all records from log and
    temporary data tables. This is a destructive operation and asks for user confirmation.
    """
    # --- Define all tables to be cleared per database ---
    trading_log_tables = [
        "live_paper_trades",
        "backtest_trades",
        "pt_portfolio_log",
        "bt_portfolio_log",
        "live_positions",
        "pt_live_debug_log",
    ]

    live_market_data_tables = [
        "live_ticks",
        "live_strategy_data",
        "live_incomplete_bars",
    ]

    print("--- Trading Log Cleanup Utility ---")
    print("This script will permanently delete all records from all log and temporary data tables.")
    
    confirm = input("\nAre you sure you want to proceed? This action cannot be undone. (y/n): ").lower()

    if confirm != 'y':
        print("Operation cancelled by user.")
        return
    
    # Clear tables in the main trading log database
    clear_database_tables(config.TRADING_DB_FILE, trading_log_tables)
    
    # Clear tables in the live market data cache database
    clear_database_tables(config.LIVE_MARKET_DB_FILE, live_market_data_tables)

if __name__ == "__main__":
    clear_logs()