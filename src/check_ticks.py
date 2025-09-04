
import duckdb
import os
import pandas as pd

# --- Configuration ---
DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'ticks.duckdb'))
TABLE_NAME = "historical_data"

def check_database_contents():
    """
    Connects to the DuckDB database, prints the total number of ticks,
    and displays the 5 most recent ticks.
    """
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file not found at {DB_FILE}")
        return

    try:
        print(f"Connecting to {DB_FILE}...")
        con = duckdb.connect(database=DB_FILE, read_only=True)

        # --- Count total ticks ---
        total_ticks_result = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE resolution = 'tick'").fetchone()
        total_ticks = total_ticks_result[0] if total_ticks_result else 0
        print(f"\nTotal number of ticks in the database: {total_ticks}")

        if total_ticks > 0:
            # --- Fetch the 5 most recent ticks ---
            print("\nFetching the 5 most recent ticks...")
            # Set pandas to display more content
            pd.set_option('display.max_rows', 10)
            pd.set_option('display.max_columns', 20)
            pd.set_option('display.width', 120)

            recent_ticks_df = con.execute(f"""
                SELECT timestamp, symbol, close as ltp, volume
                FROM {TABLE_NAME}
                WHERE resolution = 'tick' ORDER BY timestamp DESC
                LIMIT 5
            """).fetchdf()

            if not recent_ticks_df.empty:
                print(recent_ticks_df)
            else:
                print("Could not fetch recent ticks, but the table is not empty.")

        con.close()
        print("\nDatabase check complete.")

    except Exception as e:
        print(f"An error occurred while checking the database: {e}")

if __name__ == "__main__":
    check_database_contents()
