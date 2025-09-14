# src/utils/verify_db_content.py

import sqlite3
import pandas as pd
import os
import sys

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def verify_content(symbol_to_check: str):
    """
    Connects to the database and checks for data for a specific symbol.
    """
    db_file = config.HISTORICAL_MARKET_DB_FILE
    table_name = "historical_data"

    if not os.path.exists(db_file):
        print(f"Error: Database file not found at '{db_file}'.")
        return

    print(f"--- Querying Database: {db_file} ---")
    print(f"Checking for symbol: '{symbol_to_check}'")

    try:
        with sqlite3.connect(f'file:{db_file}?mode=ro', uri=True) as con:
            query = f"SELECT * FROM {table_name} WHERE symbol = ? ORDER BY timestamp DESC LIMIT 10;"
            df = pd.read_sql_query(query, con, params=(symbol_to_check,))

            if df.empty:
                print("\n❌ RESULT: No data found for this symbol.")
            else:
                print(f"\n✅ SUCCESS: Found {len(df)} records for this symbol. Here are the most recent ones:")
                print(df.to_string())
    except Exception as e:
        print(f"\nAn error occurred while querying the database: {e}")

if __name__ == "__main__":
    # We are specifically checking for the SBIN data we tried to download.
    verify_content("NSE:SBIN-EQ")