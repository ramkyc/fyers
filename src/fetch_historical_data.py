# src/fetch_historical_data.py

import sqlite3
import datetime
import os
import sys
import pandas as pd
import requests
import json
import time

# Add project root to path to allow importing config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config
from src.auth import get_fyers_model, get_access_token
from src.market_calendar import is_market_working_day

HISTORICAL_TABLE = "historical_data"
URL = "https://iislliveblob.niftyindices.com/jsonfiles/HeatmapDetail/FinalHeatmapNIFTY%2050.json"

def get_top_nifty_stocks(top_n=10):
    """Fetches the top NIFTY50 stocks by market capitalization."""
    try:
        response = requests.get(URL)
        response.raise_for_status()
        data = response.json()
        sorted_stocks = sorted(data, key=lambda x: x.get('Indexmcap_today', 0), reverse=True)
        top_stocks = []
        for stock in sorted_stocks[:top_n]:
            raw_symbol = stock['symbol']
            if not raw_symbol.endswith('-EQ') and 'INDEX' not in raw_symbol:
                top_stocks.append(f"NSE:{raw_symbol}-EQ")
            else:
                top_stocks.append(f"NSE:{raw_symbol}")
        return top_stocks
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Nifty stocks: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding Nifty stocks JSON: {e}")
        return []

def _get_date_chunks(start_date, end_date, max_days):
    """A self-contained generator to yield date chunks for API calls."""
    current_start = start_date
    while current_start <= end_date:
        current_end = current_start + datetime.timedelta(days=max_days - 1)
        if current_end > end_date:
            current_end = end_date
        yield current_start, current_end
        current_start = current_end + datetime.timedelta(days=1)

def _get_expected_counts(start_date, end_date, resolutions):
    """Calculates the expected number of candles for a given date range."""
    trading_days = 0
    current_day = start_date
    while current_day <= end_date:
        if is_market_working_day(current_day):
            trading_days += 1
        current_day += datetime.timedelta(days=1)
    
    counts = {
        "1": trading_days * 375,
        "5": trading_days * 75,
        "15": trading_days * 25,
        "30": trading_days * 13,
        "60": trading_days * 7,
        "D": trading_days * 1
    }
    return {res: counts[res] for res in resolutions}

def _build_fix_list(con, symbols, resolutions):
    """Analyzes the database and returns a dictionary of symbol/resolutions that need fixing."""
    print("\n--- Analyzing data coverage to build fix list ---")
    data_to_fix = {}
    
    start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_DAILY, "%Y-%m-%d").date()
    end_date = datetime.date.today()
    expected_counts = _get_expected_counts(start_date, end_date, resolutions)

    query = f"SELECT symbol, resolution, COUNT(*) as record_count FROM {HISTORICAL_TABLE} GROUP BY symbol, resolution;"
    actual_counts_df = pd.read_sql_query(query, con)
    
    for symbol in symbols:
        resolutions_to_fix = []
        for res in resolutions:
            expected = expected_counts.get(res, 0)
            actual_df = actual_counts_df[(actual_counts_df['symbol'] == symbol) & (actual_counts_df['resolution'] == res)]
            actual = actual_df['record_count'].iloc[0] if not actual_df.empty else 0
            
            # If the actual count is less than 99.5% of expected, mark it for fixing.
            if actual < (expected * 0.995):
                print(f"  - Flagging {symbol} ({res}): Found {actual} records, expected ~{expected}.")
                resolutions_to_fix.append(res)
        
        if resolutions_to_fix:
            data_to_fix[symbol] = resolutions_to_fix
            
    print("--- Analysis complete ---")
    return data_to_fix

def fetch_and_store_historical_data(symbols: list, resolutions: list):
    """
    Uses a simple, robust method to download and save historical data.
    This is the primary function for backfilling and repairing historical data.
    """
    print("--- Running Targeted Historical Data Fix ---")
    
    try:
        fyers = get_fyers_model(get_access_token())

        with sqlite3.connect(config.HISTORICAL_MARKET_DB_FILE, timeout=10) as con:
            cursor = con.cursor()
            print(f"Database connection opened: {config.HISTORICAL_MARKET_DB_FILE}")

            for symbol in symbols:
                print(f"\n--- Processing symbol: {symbol} ---")
                for resolution in resolutions:
                    # Use different fetching strategies for daily vs intraday
                    if resolution == "D":
                        # --- INTELLIGENT DAILY FETCH ---
                        # First, find the latest daily record we have.
                        cursor.execute(f"SELECT MAX(timestamp) FROM {HISTORICAL_TABLE} WHERE symbol = ? AND resolution = 'D'", (symbol,))
                        result = cursor.fetchone()
                        latest_timestamp_str = result[0] if result and result[0] else None

                        if latest_timestamp_str:
                            last_known_datetime = datetime.datetime.strptime(latest_timestamp_str, '%Y-%m-%d %H:%M:%S')
                            start_date = (last_known_datetime + datetime.timedelta(days=1)).date()
                        else:
                            start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_DAILY, "%Y-%m-%d").date()

                        end_date = datetime.date.today()
                        
                        if start_date <= end_date:
                            for start_chunk, end_chunk in _get_date_chunks(start_date, end_date, 30):
                                print(f"  - Fetching new D data for {symbol} from {start_chunk.strftime('%Y-%m-%d')} to {end_chunk.strftime('%Y-%m-%d')}...")
                                data = {"symbol": symbol, "resolution": "D", "date_format": "1", "range_from": start_chunk.strftime('%Y-%m-%d'), "range_to": end_chunk.strftime('%Y-%m-%d'), "cont_flag": "1"}
                                response = fyers.history(data=data)
                                if response.get("code") == 200 and response.get("candles"):
                                    candles = response["candles"]
                                    data_to_insert = [(datetime.datetime.fromtimestamp(c[0]), symbol, c[1], c[2], c[3], c[4], c[5], "D") for c in candles]
                                    cursor.executemany(f"INSERT OR IGNORE INTO {HISTORICAL_TABLE} VALUES (?,?,?,?,?,?,?,?)", data_to_insert)
                                    con.commit()
                                time.sleep(0.5) # Rate limiting
                    else: # Intraday logic
                        start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_INTRADAY, "%Y-%m-%d").date()
                        end_date = datetime.date.today()
                        print(f"  - Scanning for missing {resolution} data from {start_date} to {end_date}...")
                        current_day = start_date
                        while current_day <= end_date:
                            if not is_market_working_day(current_day):
                                current_day += datetime.timedelta(days=1)
                                continue
                            
                            date_str = current_day.strftime('%Y-%m-%d')
                            day_start = f"{date_str} 00:00:00"
                            day_end = f"{date_str} 23:59:59"
                            cursor.execute(f"SELECT 1 FROM {HISTORICAL_TABLE} WHERE symbol = ? AND resolution = ? AND timestamp BETWEEN ? AND ? LIMIT 1", (symbol, resolution, day_start, day_end))
                            if cursor.fetchone():
                                current_day += datetime.timedelta(days=1)
                                continue

                            print(f"  - Fetching {resolution} data for {symbol} on {date_str}...")
                            try:
                                data = {"symbol": symbol, "resolution": resolution, "date_format": "1", "range_from": date_str, "range_to": date_str, "cont_flag": "1"}
                                response = fyers.history(data=data)
                                if response.get("code") == 200 and response.get("candles"):
                                    candles = response["candles"]
                                    data_to_insert = [(datetime.datetime.fromtimestamp(c[0]), symbol, c[1], c[2], c[3], c[4], c[5], resolution) for c in candles]
                                    cursor.executemany(f"INSERT OR IGNORE INTO {HISTORICAL_TABLE} VALUES (?,?,?,?,?,?,?,?)", data_to_insert)
                                    con.commit()
                                    print(f"    ✅ Success: Saved {len(data_to_insert)} records.")
                                elif response.get("code") == 200:
                                    print(f"    - INFO: API returned success but no candle data.")
                                else:
                                    print(f"    ❌ FAILED: API call returned an error. Code: {response.get('code')}, Message: {response.get('message')}")
                            except Exception as e:
                                print(f"    - An error occurred during chunk fetch: {e}")
                            time.sleep(0.5) # Rate limiting
                            current_day += datetime.timedelta(days=1)

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    # --- AUTOMATED & TARGETED FIX ---
    # 1. Define the full universe of symbols and resolutions we care about.
    all_symbols = get_top_nifty_stocks(top_n=50)
    index_symbols = ["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX", "BSE:BANKEX-INDEX"]
    all_symbols.extend(index_symbols)
    all_symbols = sorted(list(set(all_symbols)))
    all_resolutions = ["D", "60", "30", "15", "5", "1"]

    # 2. Automatically build the list of what needs fixing.
    with sqlite3.connect(config.HISTORICAL_MARKET_DB_FILE, timeout=10) as con:
        data_to_fix = _build_fix_list(con, all_symbols, all_resolutions)

    # 3. Iterate through the auto-generated fix list.
    if data_to_fix:
        for symbol, resolutions in data_to_fix.items():
            fetch_and_store_historical_data([symbol], resolutions)
        print("\n--- Historical Data Fix Complete ---")
    else:
        print("\n--- Data coverage analysis complete. No significant gaps found. ---")