# src/prepare_live_data.py

import sqlite3
import datetime
import pandas as pd
import os
import sys
import json
import yaml

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config
from src.fetch_historical_data import get_top_nifty_stocks
from auth import get_fyers_model, get_access_token
from fetch_symbol_master import fetch_and_store_symbol_masters
from strategies import STRATEGY_MAPPING

def prepare_live_strategy_data(live_config: dict = None): # Add type hint for clarity
    """
    Pre-populates the `live_strategy_data` table with the most recent
    bar history needed by strategies. This script should be run before
    the market opens.
    This script is now the single source of truth for all pre-market preparation.
    """
    print(f"[{datetime.datetime.now()}] Starting daily preparation of live strategy data...")
    try:
        # --- Dynamic Configuration File Generation ---
        stocks_config_path = os.path.join(project_root, 'pt_config_stocks.yaml')

        # --- INTELLIGENT CONFIGURATION HANDLING ---
        # If the user's config file exists, load it. Otherwise, generate a default one.
        if os.path.exists(stocks_config_path):
            print(f"Found existing config at {stocks_config_path}. Loading it.")
            with open(stocks_config_path, 'r') as f:
                config_to_use = yaml.safe_load(f) or {}
        else:
            print(f"No config file found. Generating a default at {stocks_config_path}.")
            fyers_model = get_fyers_model(get_access_token())
            top_50_stocks = get_top_nifty_stocks(top_n=50)
            config_to_use = {
                'strategy': config.DEFAULT_LIVE_STRATEGY,
                'symbols': top_50_stocks,
                'paper_trade_type': 'Intraday',
                'params': {'trade_value': 100000}
            }
            with open(stocks_config_path, 'w') as f:
                yaml.dump(config_to_use, f)

        # --- Decoupled Logic: Read symbols and strategy directly from the generated files ---
        # This avoids the race condition of calling load_config() before files are ready.
        symbols_to_prepare = sorted(list(set(config_to_use.get('symbols', []))))

        if not symbols_to_prepare:
            print("No stock symbols found in config. Aborting data preparation.")
            return

        # Also ensure we prepare data for the underlying indices for the strategy's logic
        symbols_to_prepare.extend(["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX", "BSE:BANKEX-INDEX"])
        strategy_name = config_to_use.get('strategy', config.DEFAULT_LIVE_STRATEGY)

        # 2. Instantiate the strategy to ask it what data it needs
        strategy_class = STRATEGY_MAPPING.get(strategy_name)
        if not strategy_class:
            print(f"Strategy '{strategy_name}' not found. Cannot prepare data.")
            return
        
        # --- DEFINITIVE FIX: Read the configured timeframes ---
        # Use the timeframes from the config, plus '1' for resampling and 'D' for strategy logic.
        configured_timeframes = config_to_use.get('timeframes', ['1', '5', '15', '30', '60'])
        # We instantiate it with dummy portfolio/oms because we only need its parameters
        # CRITICAL: We must provide a primary resolution to get the correct required resolutions.
        strategy_instance = strategy_class(symbols=[], params=config_to_use.get('params', {}), primary_resolution=configured_timeframes[0] if configured_timeframes else '1')

        live_timeframes = list(set(configured_timeframes + ['1', 'D']))
        required_resolutions = sorted(list(set(strategy_instance.get_required_resolutions() + live_timeframes)))

        required_history_len = 100 # A safe number to cover most lookback periods

        # 4. Connect to databases
        hist_con = sqlite3.connect(f'file:{config.HISTORICAL_MARKET_DB_FILE}?mode=ro', uri=True)
        live_con = sqlite3.connect(config.LIVE_MARKET_DB_FILE)
        live_cursor = live_con.cursor()

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

        live_con.commit()


    except Exception as e:
        print(f"An error occurred during live data preparation: {e}")
    finally:
        if 'hist_con' in locals(): hist_con.close()
        if 'live_con' in locals(): live_con.close()
        print(f"[{datetime.datetime.now()}] Live strategy data preparation finished.")

if __name__ == "__main__":
    prepare_live_strategy_data() # Running standalone uses defaults