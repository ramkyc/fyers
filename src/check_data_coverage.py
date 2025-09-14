# src/check_data_coverage.py

import sqlite3
import pandas as pd
import os
import argparse
import sys

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def check_data_coverage(pivot_view=False):
    """
    Connects to the historical data database and prints a summary of the
    data coverage for each symbol and resolution.
    """
    db_file = config.HISTORICAL_MARKET_DB_FILE
    table_name = "historical_data"

    if not os.path.exists(db_file):
        print(f"Error: Database file not found at '{db_file}'.")
        print("Please run 'python src/fetch_historical_data.py' to create and populate it.")
        return

    print(f"--- Checking Data Coverage in {db_file} ---")

    try:
        with sqlite3.connect(f'file:{db_file}?mode=ro', uri=True) as con:
            # Check if the table exists
            cursor = con.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if cursor.fetchone() is None:
                print(f"Error: Table '{table_name}' not found in the database.")
                return

            query = f"""
                SELECT
                    symbol,
                    resolution,
                    COUNT(*) as record_count,
                    MIN(timestamp) as earliest_record,
                    MAX(timestamp) as latest_record
                FROM
                    {table_name}
                GROUP BY
                    symbol, resolution
                ORDER BY
                    symbol, CASE WHEN resolution = 'D' THEN 999 ELSE CAST(resolution AS INTEGER) END;
            """
            
            df = pd.read_sql_query(query, con)

            if df.empty:
                print("No data found in the historical_data table.")
            else:
                # Calculate the total before any string formatting
                total_records = df['record_count'].sum()

                if pivot_view:
                    print("\n--- Data Coverage Pivot Table (Record Counts) ---")
                    # The 'record_count' is already an integer from the SQL query
                    pivot_df = df.pivot_table(
                        index='symbol',
                        columns='resolution',
                        values='record_count',
                        aggfunc='sum', # Use sum, though each group should be unique
                        fill_value=0   # Show 0 for missing combinations
                    )
                    # Ensure columns are in a logical order
                    desired_columns = [res for res in ["D", "60", "30", "15", "5", "1"] if res in pivot_df.columns]
                    pivot_df = pivot_df[desired_columns]
                    # Format with commas for readability
                    print(pivot_df.applymap('{:,}'.format).to_string())
                else:
                    df['record_count'] = df['record_count'].map('{:,}'.format)
                    print(df.to_string())
                
                # Print the total at the end
                print(f"\n--- Total Records in Table: {total_records:,} ---")

    except Exception as e:
        print(f"An error occurred while checking data coverage: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check historical data coverage.")
    parser.add_argument("--pivot", action="store_true", help="Display the data coverage as a pivot table.")
    args = parser.parse_args()
    check_data_coverage(pivot_view=args.pivot)