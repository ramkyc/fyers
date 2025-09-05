# src/archive_live_data.py

import sqlite3
import os
import sys
import datetime

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

SOURCE_DB = config.LIVE_MARKET_DB_FILE
DEST_DB = config.HISTORICAL_MARKET_DB_FILE
SOURCE_TABLE = "live_ticks"
DEST_TABLE = "historical_ticks"

def archive_live_ticks():
    """
    Moves live tick data from the live database to the historical database
    and then clears the live tick table for the next day.
    This script is intended to be run after market close.
    """
    print(f"[{datetime.datetime.now()}] Starting live tick data archiving process...")

    if not os.path.exists(SOURCE_DB):
        print(f"Source database '{SOURCE_DB}' not found. Nothing to archive. Exiting.")
        return

    try:
        # Connect to both databases
        source_con = sqlite3.connect(SOURCE_DB)
        dest_con = sqlite3.connect(DEST_DB)
        source_cursor = source_con.cursor()
        dest_cursor = dest_con.cursor()

        # 1. Create the destination table if it doesn't exist
        dest_cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {DEST_TABLE} (
                timestamp TIMESTAMP,
                symbol TEXT,
                ltp REAL,
                volume INTEGER,
                UNIQUE(timestamp, symbol)
            );
        """)
        print(f"Destination table '{DEST_TABLE}' in '{DEST_DB}' is ready.")

        # 2. Read all data from the source table
        source_cursor.execute(f"SELECT * FROM {SOURCE_TABLE}")
        ticks_to_archive = source_cursor.fetchall()

        if not ticks_to_archive:
            print("No new ticks found in the live database. Archiving complete.")
            return

        print(f"Found {len(ticks_to_archive)} ticks to archive.")

        # 3. Insert data into the destination table
        dest_cursor.executemany(f"INSERT OR IGNORE INTO {DEST_TABLE} VALUES (?, ?, ?, ?)", ticks_to_archive)
        dest_con.commit()
        print(f"Successfully inserted ticks into '{DEST_TABLE}'.")

        # 4. Clear the source table
        source_cursor.execute(f"DELETE FROM {SOURCE_TABLE}")
        source_con.commit()
        print(f"Cleared source table '{SOURCE_TABLE}' for the next trading day.")

    except Exception as e:
        print(f"An error occurred during the archiving process: {e}")
    finally:
        if 'source_con' in locals(): source_con.close()
        if 'dest_con' in locals(): dest_con.close()
        print(f"[{datetime.datetime.now()}] Archiving process finished.")

if __name__ == "__main__":
    archive_live_ticks()