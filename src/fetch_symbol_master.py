# src/fetch_symbol_master.py

import pandas as pd
import sqlite3
import os
import sys
import datetime
import glob

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config

MASTER_URLS = {
    "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM.csv",
    "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO.csv",
    "BSE_CM": "https://public.fyers.in/sym_details/BSE_CM.csv",
    "BSE_FO": "https://public.fyers.in/sym_details/BSE_FO.csv",
}

DEST_DB = config.HISTORICAL_MARKET_DB_FILE
DEST_TABLE = "symbol_master"

def fetch_and_store_symbol_masters():
    """
    Downloads the symbol master files from Fyers, processes them,
    and stores the relevant details in the historical database.
    Creates a stamp file to indicate completion for the day.
    """
    print(f"[{datetime.datetime.now()}] Starting symbol master download...")

    # --- Cleanup old stamp files ---
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    stamp_pattern = os.path.join(config.DATA_DIR, 'symbol_master_*.stamp')
    for old_stamp_file in glob.glob(stamp_pattern):
        if today_str not in os.path.basename(old_stamp_file):
            try:
                os.remove(old_stamp_file)
                print(f"  - Cleaned up old stamp file: {os.path.basename(old_stamp_file)}")
            except OSError as e:
                print(f"  - Warning: Could not remove old stamp file {old_stamp_file}. Error: {e}")


    all_symbols_list = []

    # Define column names as per Fyers documentation. This list has 20 elements.
    column_names = [
        'fy_token', 'symbol_details', 'exchange_token', 'symbol_ticker',
        'instrument_type', 'min_lot', 'tick_size', 'isin', 'trading_session',
        'last_updated', 'expiry_date', 'symbol_id', 'exchange', 'segment',
        'lot_size', 'underlying_id', 'underlying_isin', 'strike_price', 'option_type', 'extra_data'
    ]

    for segment, url in MASTER_URLS.items():
        try:
            print(f"  - Downloading master for {segment} from {url}...")
            df = pd.read_csv(url, header=None, names=column_names, usecols=range(len(column_names)))
            all_symbols_list.append(df)
            print(f"  - Processed {len(df)} symbols for {segment}.")

        except Exception as e:
            print(f"  - ERROR: Could not download or process master for {segment}. Reason: {e}")

    if all_symbols_list:
        # Combine all dataframes into one
        combined_df = pd.concat(all_symbols_list, ignore_index=True)

        # Select only the columns we need from the combined dataframe
        final_df = combined_df[[
            'fy_token', 'symbol_ticker', 'symbol_details', 'lot_size', 
            'instrument_type', 'underlying_id', 'strike_price', 'option_type', 'expiry_date'
        ]]

        try:
            with sqlite3.connect(DEST_DB) as con:
                # Store the combined data into the database, replacing the old table
                final_df.to_sql(DEST_TABLE, con, if_exists='replace', index=False)
                print(f"\nSuccessfully stored {len(final_df)} total symbols in '{DEST_TABLE}' table.")

                # --- Create stamp file on success ---
                stamp_file_path = os.path.join(config.DATA_DIR, f'symbol_master_{today_str}.stamp')
                with open(stamp_file_path, 'w') as f:
                    f.write(datetime.datetime.now().isoformat())
                print(f"Created success stamp file: {os.path.basename(stamp_file_path)}")

        except Exception as e:
            print(f"\nERROR: Could not write symbol master data to database. Reason: {e}")

    print(f"[{datetime.datetime.now()}] Symbol master download finished.")

if __name__ == "__main__":
    # Ensure the database setup has been run
    if not os.path.exists(config.DATA_DIR):
        os.makedirs(config.DATA_DIR)
    
    fetch_and_store_symbol_masters()