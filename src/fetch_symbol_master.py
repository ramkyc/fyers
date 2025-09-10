# src/fetch_symbol_master.py

import pandas as pd
import sqlite3
import os
import sys
import datetime

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
    """
    print(f"[{datetime.datetime.now()}] Starting symbol master download...")

    all_symbols_df = pd.DataFrame()

    # Define column names as per Fyers documentation. This list has 20 elements.
    column_names = [
        'fy_token', 'symbol_details', 'exchange_token', 'symbol_ticker',
        'instrument_type', 'min_lot', 'tick_size', 'isin', 'trading_session',
        'last_updated', 'expiry_date', 'symbol_id', 'exchange', 'segment',
        'lot_size', 'underlying_id', 'underlying_isin', 'strike_price',
        'option_type', 'extra_data'
    ]

    for segment, url in MASTER_URLS.items():
        try:
            print(f"  - Downloading master for {segment} from {url}...")
            # Read the CSV, explicitly using only the first 20 columns to avoid
            # errors from trailing commas in the source file.
            df = pd.read_csv(url, header=None, names=column_names, usecols=range(len(column_names)))

            # Select only the columns we need
            df_filtered = df[['symbol_ticker', 'symbol_details', 'lot_size', 'instrument_type', 'underlying_id', 'strike_price', 'option_type', 'expiry_date']]
            
            # Append to the main DataFrame
            all_symbols_df = pd.concat([all_symbols_df, df_filtered], ignore_index=True)
            print(f"  - Processed {len(df)} symbols for {segment}.")

        except Exception as e:
            print(f"  - ERROR: Could not download or process master for {segment}. Reason: {e}")

    if not all_symbols_df.empty:
        try:
            with sqlite3.connect(DEST_DB) as con:
                # Store the combined data into the database, replacing the old table
                all_symbols_df.to_sql(DEST_TABLE, con, if_exists='replace', index=False)
                print(f"\nSuccessfully stored {len(all_symbols_df)} total symbols in '{DEST_TABLE}' table.")
        except Exception as e:
            print(f"\nERROR: Could not write symbol master data to database. Reason: {e}")

    print(f"[{datetime.datetime.now()}] Symbol master download finished.")

if __name__ == "__main__":
    # Ensure the database setup has been run
    if not os.path.exists(config.DATA_DIR):
        os.makedirs(config.DATA_DIR)
    
    fetch_and_store_symbol_masters()