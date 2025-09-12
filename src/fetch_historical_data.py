import json
import requests
from fyers_apiv3 import fyersModel
import datetime
import sqlite3
import os
from dateutil.relativedelta import relativedelta

import sys # Add the project root to the Python path to allow absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.auth import get_fyers_model, get_access_token
from src.market_calendar import is_market_working_day, get_trading_holidays
import config # config.py is now in the project root

URL = "https://iislliveblob.niftyindices.com/jsonfiles/HeatmapDetail/FinalHeatmapNIFTY%2050.json"
HISTORICAL_TABLE = "historical_data"

def get_top_nifty_stocks(top_n=10):
    """
    Fetches the top NIFTY50 stocks by market capitalization.

    Args:
        top_n (int): The number of top stocks to return.

    Returns:
        list: A list of the top N stock symbols formatted for Fyers API.
    """
    try:
        response = requests.get(URL)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        # Sort the stocks by market capitalization (Indexmcap_today)
        sorted_stocks = sorted(data, key=lambda x: x.get('Indexmcap_today', 0), reverse=True)

        # Get the top N stock symbols and format them
        top_stocks = []
        for stock in sorted_stocks[:top_n]:
            raw_symbol = stock['symbol']
            # The Fyers history API expects the raw symbol (e.g., 'M&M'), not a URL-encoded one ('M%26M').
            # The rule is: if it's not an index and doesn't already end in -EQ, add -EQ.
            # Symbols like BAJAJ-AUTO need to become BAJAJ-AUTO-EQ.
            # Symbols like M&M need to become M&M-EQ.
            if not raw_symbol.endswith('-EQ') and 'INDEX' not in raw_symbol:
                top_stocks.append(f"NSE:{raw_symbol}-EQ")
            else:
                top_stocks.append(f"NSE:{raw_symbol}")

        return top_stocks

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return []

def _get_max_days_for_resolution(resolution: str) -> int:
    """Returns the maximum number of days of data that can be fetched in one API call for a given resolution."""
    if resolution in ["1", "2", "3"]:
        return 50  # Fyers limit is ~60 days, 50 is a safe buffer
    elif resolution in ["5", "10", "15", "20", "30"]:
        return 90  # Fyers limit is ~100 days, 90 is a safe buffer
    elif resolution in ["60", "120", "240"]:  # Hourly resolutions
        return 90  # The API is very sensitive to date ranges for hourly data. A smaller chunk size is more reliable.
    elif resolution == "D":
        return 365 * 2 # Daily data can be fetched for many years, but API rejects very large ranges. 2 years is a safe chunk.
    else:
        return 30 # Default to a safe value

def _get_date_chunks(start_date, end_date, max_days):
    """Generator to yield date chunks for API calls."""
    current_start = start_date
    while current_start <= end_date:
        current_end = current_start + datetime.timedelta(days=max_days - 1)
        if current_end > end_date:
            current_end = end_date
        yield current_start, current_end
        current_start = current_end + datetime.timedelta(days=1)

def fetch_and_store_historical_data(fyers: fyersModel.FyersModel, symbols: list, resolutions: list, mode: str = 'backfill'):
    """
    Fetches historical data for a list of symbols across multiple resolutions
    and stores it in a SQLite database.
    
    Args:
        fyers (fyersModel.FyersModel): An authenticated fyersModel instance.
        symbols (list): A list of stock symbols (e.g., ["NSE:SBIN-EQ"])
        resolutions (list): A list of data resolutions (e.g., ["D", "60", "15", "5", "1"])
        mode (str): 'backfill' for comprehensive history, 'live_startup' for fetching only recent data.
    """
    # The db_setup.py script is now responsible for all table creation.
    # We will connect and disconnect for each symbol to minimize db lock time.

    # Fetch data up to today. The API handles partial candles correctly.

    for symbol in symbols:
        print(f"\n--- Processing symbol: {symbol} ---")

        # Connect to the database for the current symbol.
        # This ensures the database is not locked for the entire duration of the script.
        try:
            con = sqlite3.connect(config.HISTORICAL_MARKET_DB_FILE, timeout=10) # Use a timeout
            cursor = con.cursor()
        except sqlite3.OperationalError as e:
            print(f"Could not connect to database for symbol {symbol}. Error: {e}. Skipping.")
            continue

        for resolution in resolutions:
            overall_end_date = datetime.date.today()

            if mode == 'live_startup':
                # For live startup, we only need the last ~100 candles. We fetch a bit more to be safe.
                # We calculate a rough start date and fetch in one chunk.
                days_to_fetch = 3 if resolution != 'D' else 150 # 3 days for intraday, 150 for daily
                start_date_for_fetch = overall_end_date - datetime.timedelta(days=days_to_fetch)
                print(f"  - Fetching recent data for {symbol} ({resolution})...")
                try:
                    data = {"symbol": symbol, "resolution": resolution, "date_format": "1", "range_from": start_date_for_fetch.strftime('%Y-%m-%d'), "range_to": overall_end_date.strftime('%Y-%m-%d'), "cont_flag": "1"}
                    response = fyers.history(data=data)

                    if response.get("code") == 200 and response.get("candles"):
                        candles = response["candles"][-100:] # Take only the last 100 candles
                        data_to_insert = [(datetime.datetime.fromtimestamp(c[0]), symbol, c[1], c[2], c[3], c[4], c[5], resolution) for c in candles]
                        # For live startup, we replace existing data to ensure it's fresh.
                        cursor.execute(f"DELETE FROM {HISTORICAL_TABLE} WHERE symbol = ? AND resolution = ?", (symbol, resolution))
                        cursor.executemany(f"INSERT INTO {HISTORICAL_TABLE} (timestamp, symbol, open, high, low, close, volume, resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", data_to_insert)
                        con.commit()
                except Exception as e:
                    print(f"    - An error occurred during recent data fetch: {e}")

            elif mode == 'backfill':
                # For backfill, use the existing intelligent, incremental logic.
                cursor.execute(f"SELECT MAX(timestamp) FROM {HISTORICAL_TABLE} WHERE symbol = ? AND resolution = ?", (symbol, resolution))
                latest_timestamp_str = cursor.fetchone()[0]
                
                if latest_timestamp_str:
                    last_known_datetime = datetime.datetime.strptime(latest_timestamp_str, '%Y-%m-%d %H:%M:%S')
                    overall_start_date = (last_known_datetime + datetime.timedelta(seconds=1)).date()
                    print(f"Existing data found for {symbol} ({resolution}). Last entry: {latest_timestamp_str}. Fetching new data since then.")
                else:
                    if resolution == "D":
                        overall_start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_DAILY, "%Y-%m-%d").date()
                    else:
                        overall_start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_INTRADAY, "%Y-%m-%d").date()
                    print(f"No existing data for {symbol} ({resolution}). Fetching full range from {overall_start_date}.")
                
                current_date = overall_start_date
                while current_date <= overall_end_date:
                    if not is_market_working_day(current_date):
                        current_date += datetime.timedelta(days=1)
                        continue

                    date_str = current_date.strftime('%Y-%m-%d')
                    
                    cursor.execute(f"SELECT 1 FROM {HISTORICAL_TABLE} WHERE symbol = ? AND resolution = ? AND date(timestamp) = ? LIMIT 1", (symbol, resolution, date_str))
                    if cursor.fetchone() and current_date != overall_end_date:
                        current_date += datetime.timedelta(days=1)
                        continue

                    print(f"  - Fetching data for {symbol} ({resolution}) on {date_str}...")
                    try:
                        data = {"symbol": symbol, "resolution": resolution, "date_format": "1", "range_from": date_str, "range_to": date_str, "cont_flag": "1"}
                        response = fyers.history(data=data)

                        if response.get("code") == 200 and response.get("candles"):
                            candles = response["candles"]
                            data_to_insert = [(datetime.datetime.fromtimestamp(c[0]), symbol, c[1], c[2], c[3], c[4], c[5], resolution) for c in candles]
                            cursor.executemany(f"INSERT OR IGNORE INTO {HISTORICAL_TABLE} (timestamp, symbol, open, high, low, close, volume, resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", data_to_insert)
                            con.commit()
                    except Exception as e:
                        print(f"    - An error occurred during daily fetch: {e}")
                    
                    current_date += datetime.timedelta(days=1)

        # Close the connection after processing all resolutions for the current symbol
        if 'con' in locals() and con:
            con.close()
            print(f"Connection closed for symbol {symbol}.")

def get_historical_expiry(trade_date: datetime.date, index_name: str) -> datetime.date:
    """
    Calculates the nearest future expiry date for a given historical trade date.
    NOTE: This is a simplified implementation. A production system would need a more robust
    holiday calendar and handling for expiry day shifts.
    """
    holidays = get_trading_holidays(trade_date.year)
    
    # NIFTY & BANKNIFTY have weekly expiries on Thursdays
    if index_name in ["NIFTY", "BANKNIFTY"]:
        days_to_thursday = (3 - trade_date.weekday() + 7) % 7
        expiry_date = trade_date + datetime.timedelta(days=days_to_thursday)
        # If expiry falls on a holiday, move to the previous working day
        while expiry_date in holidays or expiry_date.weekday() >= 5:
            expiry_date -= datetime.timedelta(days=1)
        return expiry_date
        
    # SENSEX & BANKEX have monthly expiries on the last Friday
    elif index_name in ["SENSEX", "BANKEX"]:
        # Find the last day of the month
        next_month = trade_date.replace(day=28) + datetime.timedelta(days=4)
        last_day_of_month = next_month - datetime.timedelta(days=next_month.day)
        
        # Find the last Friday of the month
        expiry_date = last_day_of_month
        while expiry_date.weekday() != 4: # 4 is Friday
            expiry_date -= datetime.timedelta(days=1)
            
        # If expiry falls on a holiday, move to the previous working day
        while expiry_date in holidays or expiry_date.weekday() >= 5:
            expiry_date -= datetime.timedelta(days=1)
        return expiry_date
        
    return None

def fetch_historical_options_data(fyers: fyersModel.FyersModel, start_date: datetime.date, end_date: datetime.date):
    """
    Fetches historical 1-minute data for ATM options for a given date range.
    """
    print("\n--- Starting Historical Options Data Fetch ---")
    
    indices = {
        "NIFTY": {"symbol": "NSE:NIFTY50-INDEX", "strike_interval": 100, "name": "NIFTY", "exchange": "NSE"},
        "BANKNIFTY": {"symbol": "NSE:NIFTYBANK-INDEX", "strike_interval": 100, "name": "BANKNIFTY", "exchange": "NSE"},
    }
    
    current_date = start_date
    while current_date <= end_date:
        if not is_market_working_day(current_date):
            current_date += datetime.timedelta(days=1)
            continue
            
        print(f"\nProcessing options for date: {current_date.strftime('%Y-%m-%d')}")
        
        for index_name, index_data in indices.items():
            try:
                # 1. Get the opening price of the index for that day to find the ATM strike
                hist_data = {
                    "symbol": index_data["symbol"], "resolution": "1", "date_format": "1",
                    "range_from": current_date.strftime("%Y-%m-%d"), "range_to": current_date.strftime("%Y-%m-%d"), "cont_flag": "1"
                }
                response = fyers.history(data=hist_data)
                
                if not (response.get("code") == 200 and response.get("candles")):
                    print(f"  - Could not fetch index price for {index_name} on {current_date}. Skipping.")
                    continue
                
                open_price = response["candles"][0][1] # Get the open of the first 1-min candle
                atm_strike = round(open_price / index_data["strike_interval"]) * index_data["strike_interval"]
                
                # 2. Calculate the historical expiry date
                expiry_date = get_historical_expiry(current_date, index_name)
                if not expiry_date:
                    continue
                
                # 3. Construct the option symbols
                year = str(expiry_date.year)[-2:]
                month = expiry_date.strftime("%b").upper()
                
                ce_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}CE"
                pe_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}PE"
                
                # 4. Fetch and store data for these two option symbols for the current day
                for option_symbol in [ce_symbol, pe_symbol]:
                    # --- Intelligent Fetch: Check if data already exists ---
                    with sqlite3.connect(config.HISTORICAL_MARKET_DB_FILE, timeout=10) as con:
                        cursor = con.cursor()
                        # Check for any record for this symbol on this day.
                        # We use LIKE to match any timestamp within the given day.
                        cursor.execute("""
                            SELECT 1 FROM historical_data 
                            WHERE symbol = ? AND resolution = '1' AND date(timestamp) = ? 
                            LIMIT 1
                        """, (option_symbol, current_date.strftime('%Y-%m-%d')))
                        
                        if cursor.fetchone():
                            print(f"  - Data for {option_symbol} on {current_date} already exists. Skipping.")
                        else:
                            _fetch_and_store_chunk(fyers, option_symbol, "1", current_date, current_date, cursor)
                            con.commit()
            except Exception as e:
                print(f"  - Error processing {index_name} for {current_date}: {e}")

        current_date += datetime.timedelta(days=1)

if __name__ == "__main__":
    try:
        print("-------------------- Starting Historical Data Fetch --------------------")
        
        # 1. Initialize the Fyers model
        access_token = get_access_token()
        fyers = get_fyers_model(access_token)

        # 2. Get the list of symbols to fetch
        # Fetch the full Nifty 50 for more comprehensive backtesting options
        symbols_to_fetch = get_top_nifty_stocks(top_n=50)
        # CRITICAL FIX: Also fetch data for the underlying indices, which are needed by strategies.
        index_symbols = ["NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX", "BSE:BANKEX-INDEX"]
        symbols_to_fetch.extend(index_symbols)
        symbols_to_fetch = sorted(list(set(symbols_to_fetch))) # Remove duplicates and sort
        print(f"\nFetching data for the following symbols: {symbols_to_fetch}")

        # 3. Define the resolutions to fetch
        resolutions_to_fetch = ["D", "60", "30", "15", "5", "1"]

        # 4. Fetch and store the data for all resolutions
        fetch_and_store_historical_data(
            fyers=fyers,
            symbols=symbols_to_fetch,
            resolutions=resolutions_to_fetch,
            mode='backfill' # Explicitly set to backfill mode when run manually
        )

        print("-------------------- Historical Data Fetch Complete --------------------")

    except Exception as e:
        print(f"An error occurred in the main execution block: {e}")
        print("Please ensure your '.env' file is set up and you have a valid 'fyers_tokens.json'.")
        print("You can generate tokens by running 'python src/auth.py' manually.")
