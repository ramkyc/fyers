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
from fetch_historical_data import get_top_nifty_stocks
from auth import get_fyers_model, get_access_token
from fetch_symbol_master import fetch_and_store_symbol_masters
from strategies import STRATEGY_MAPPING

def prepare_live_strategy_data():
    """
    Pre-populates the `live_strategy_data` table with the most recent
    bar history needed by strategies. This script should be run before
    the market opens.
    This script is now the single source of truth for all pre-market preparation.
    """
    print(f"[{datetime.datetime.now()}] Starting daily preparation of live strategy data...")
    try:
        # --- Dynamic Configuration File Generation ---
        fyers_model = get_fyers_model(get_access_token())
        
        # 1. Generate pt_config_stocks.yaml
        top_10_stocks = get_top_nifty_stocks(top_n=10)
        stocks_config_path = os.path.join(project_root, 'pt_config_stocks.yaml')
        default_stock_config = {
            'strategy': config.DEFAULT_LIVE_STRATEGY,
            'symbols': top_10_stocks,
            'paper_trade_type': 'Intraday',
            'params': {'trade_value': 100000} # A safe default
        }
        with open(stocks_config_path, 'w') as f:
            yaml.dump(default_stock_config, f)
        print(f"Generated default stock config at {stocks_config_path}")


        # --- Decoupled Logic: Read symbols and strategy directly from the generated files ---
        # This avoids the race condition of calling load_config() before files are ready.
        # --- SIMPLIFIED: Only use symbols from the stocks config ---
        symbols_to_prepare = sorted(list(set(default_stock_config.get('symbols', []))))

        if not symbols_to_prepare:
            print("No stock symbols found in config. Aborting data preparation.")
            return

        # Also ensure we prepare data for the underlying indices for the strategy's logic
        symbols_to_prepare.extend(["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX", "BSE:BANKEX-INDEX"])
        strategy_name = default_stock_config.get('strategy', config.DEFAULT_LIVE_STRATEGY)

        # 2. Instantiate the strategy to ask it what data it needs
        strategy_class = STRATEGY_MAPPING.get(strategy_name)
        if not strategy_class:
            print(f"Strategy '{strategy_name}' not found. Cannot prepare data.")
            return
        
        # We instantiate it with dummy portfolio/oms because we only need its parameters
        strategy_instance = strategy_class(symbols=[], params=default_stock_config.get('params', {}), resolutions=['1'])
        # Ensure we always fetch 1-minute data for the live charts, in addition to what the strategy needs.
        # Critical Fix: The live engine runs on all these timeframes, so we must prepare data for all of them.
        live_timeframes = ['1', '5', '15', '30', '60', 'D'] # CRITICAL FIX: Add 'D' for daily data
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
    prepare_live_strategy_data()