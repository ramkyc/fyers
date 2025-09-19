# tools/view_debug_log.py

import argparse
import sqlite3
import pandas as pd
import json
import os
import sys

# --- Add project root to sys.path ---
# Since this script is in src/utils, we need to go up two levels to reach the project root.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

def view_log(run_id: str, tail: int, symbol: str = None):
    """
    Connects to the database and displays strategy decision logs for a given run_id.
    """
    db_path = config.TRADING_DB_FILE
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at '{db_path}'")
        return

    print(f"--- Querying Strategy Decision Logs for Run ID: {run_id} ---")

    try:
        with sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) as con:
            query = "SELECT timestamp, log_data FROM pt_live_debug_log WHERE run_id = ? ORDER BY timestamp DESC;"
            df = pd.read_sql_query(query, con, params=(run_id,))

        if df.empty:
            print("No debug logs found for this Run ID.")
            return

        # Parse the JSON log data
        parsed_logs = [json.loads(row['log_data']) for _, row in df.iterrows()]

        # Filter for actual strategy decision logs
        strategy_decision_logs = [
            log for log in parsed_logs
            if isinstance(log, dict) and log.get('message') == "Strategy Decision" and 'data' in log and isinstance(log['data'], dict)
        ]

        if not strategy_decision_logs:
            print("Found debug logs, but none were marked as 'Strategy Decision'.")
            return

        # Convert to DataFrame for easy viewing
        strategy_df = pd.DataFrame([log['data'] for log in strategy_decision_logs])

        # --- FIX: Ensure DataFrame is sorted by timestamp before applying tail ---
        # The original order from the DB query is not always preserved when creating the DataFrame.
        # We must explicitly sort by the timestamp from the log data to ensure 'tail' works correctly.
        strategy_df = strategy_df.sort_values(by='timestamp', ascending=False)

        # Apply optional symbol filter
        if symbol:
            strategy_df = strategy_df[strategy_df['symbol'].str.contains(symbol, case=False, na=False)]
            print(f"Filtering for symbol containing '{symbol}'...")

        # Apply tail
        if tail > 0:
            strategy_df = strategy_df.head(tail)
            print(f"Showing the last {len(strategy_df)} of {len(strategy_decision_logs)} decision logs...")

        # Display the results
        if not strategy_df.empty:
            pd.set_option('display.width', 1000)
            pd.set_option('display.max_columns', 20)
            print(strategy_df.to_string())
        else:
            print("No matching strategy decision logs found after filtering.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="View strategy decision logs from the database.")
    parser.add_argument("run_id", help="The run_id of the session to analyze (e.g., 'live_20231027_103000').")
    parser.add_argument("-t", "--tail", type=int, default=50, help="Number of recent logs to display. Set to 0 for all logs. Default is 50.")
    parser.add_argument("-s", "--symbol", type=str, default=None, help="Filter logs for a specific symbol.")

    args = parser.parse_args()
    view_log(args.run_id, args.tail, args.symbol)

    print("\nUsage Example: python src/utils/view_debug_log.py live_20231027_103000 --tail 100 --symbol RELIANCE")