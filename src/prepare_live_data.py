# src/prepare_live_data.py

import sqlite3
import datetime
import pandas as pd
import os
import sys
import json

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config
from src.fetch_historical_data import get_top_nifty_stocks, get_atm_option_symbols
from src.auth import get_fyers_model, get_access_token
from src.fetch_symbol_master import fetch_and_store_symbol_masters
from src.strategies import STRATEGY_MAPPING

def prepare_live_strategy_data():
    """
    Pre-populates the `live_strategy_data` table with the most recent
    bar history needed by strategies. This script should be run before
    the market opens.
    """
    print(f"[{datetime.datetime.now()}] Starting daily preparation of live strategy data...")

    today_str = datetime.date.today().strftime('%Y-%m-%d')
    marker_file = os.path.join(config.DATA_DIR, f"live_data_prepared_for_{today_str}.txt")

    if os.path.exists(marker_file):
        print(f"Live strategy data has already been prepared for {today_str}. Skipping.")
        return

    try:
        # --- Daily Symbol Master Sync ---
        # As per the user's request, we sync the master data once per day
        # at the start of the pre-market preparation process.
        fetch_and_store_symbol_masters()

        # 1. Load the live configuration to see which strategy is selected
        from src.live_config_manager import load_config
        live_config, msg = load_config()
        if not live_config:
            print(f"Could not prepare live data: {msg}")
            return

        # 2. Instantiate the strategy to ask it what data it needs
        strategy_class = STRATEGY_MAPPING.get(live_config['strategy'])
        if not strategy_class:
            print(f"Strategy '{live_config['strategy']}' not found. Cannot prepare data.")
            return
        
        # We instantiate it with dummy portfolio/oms because we only need its parameters
        strategy_instance = strategy_class(symbols=[], portfolio=None, order_manager=None, params=live_config['params'])
        required_resolutions = strategy_instance.get_required_resolutions()
        print(f"Strategy '{live_config['strategy']}' requires resolutions: {required_resolutions}")

        # 3. Determine the symbols that will be traded today
        fyers_model = get_fyers_model(get_access_token())
        tradeable_symbols = get_top_nifty_stocks(top_n=50)
        atm_options = get_atm_option_symbols(fyers_model)
        symbols_to_prepare = tradeable_symbols + atm_options

        required_history_len = 100 # A safe number to cover most lookback periods

        # 4. Connect to databases
        hist_con = sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True)
        live_con = sqlite3.connect(config.LIVE_MARKET_DB_FILE)
        live_cursor = live_con.cursor()

        # Ensure the target table exists
        live_cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_strategy_data (
                timestamp TIMESTAMP,
                symbol TEXT,
                resolution TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER,
                UNIQUE(symbol, resolution, timestamp)
            );
        """)

        # 5. Clear the old data from the live strategy table
        live_cursor.execute("DELETE FROM live_strategy_data;")
        print("Cleared old live strategy data.")

        # 6. Fetch recent history for each symbol and resolution and insert into the live table
        for resolution in required_resolutions:
            for symbol in symbols_to_prepare:
                query = """
                    SELECT timestamp, symbol, open, high, low, close, volume
                    FROM historical_data
                    WHERE symbol = ? AND resolution = ?
                    ORDER BY timestamp DESC
                    LIMIT ?;
                """
                df = pd.read_sql_query(query, hist_con, params=(symbol, resolution, required_history_len))

                if not df.empty:
                    df['resolution'] = resolution
                    df = df[['timestamp', 'symbol', 'resolution', 'open', 'high', 'low', 'close', 'volume']]
                    df.to_sql('live_strategy_data', live_con, if_exists='append', index=False)
                    print(f"  - Prepared {len(df)} bars for {symbol} at {resolution} resolution.")

        # 7. Save the full list of prepared symbols for the dashboard to use
        live_symbols_file = os.path.join(config.DATA_DIR, 'live_symbols.json')
        with open(live_symbols_file, 'w') as f:
            json.dump(symbols_to_prepare, f)
        print(f"Saved {len(symbols_to_prepare)} tradeable symbols to {live_symbols_file}")

        live_con.commit()

        # 8. Create the marker file to indicate successful preparation
        with open(marker_file, 'w') as f:
            f.write(f"Data prepared at {datetime.datetime.now()}")
        print(f"Successfully created marker file: {marker_file}")

    except Exception as e:
        print(f"An error occurred during live data preparation: {e}")
    finally:
        if 'hist_con' in locals(): hist_con.close()
        if 'live_con' in locals(): live_con.close()
        print(f"[{datetime.datetime.now()}] Live strategy data preparation finished.")

if __name__ == "__main__":
    prepare_live_strategy_data()