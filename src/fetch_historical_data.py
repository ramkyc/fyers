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
            # Some symbols from the source (like 'ITC') already contain a hyphen in their Fyers representation ('ITC-EQ').
            # To avoid creating an invalid symbol like 'NSE:ITC-EQ-EQ', we check before appending '-EQ'.
            if '-' in raw_symbol:
                top_stocks.append(f"NSE:{raw_symbol}")
            else:
                top_stocks.append(f"NSE:{raw_symbol}-EQ")

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

def _fetch_and_store_chunk(fyers, symbol, resolution, start_date, end_date, cursor):
    """Fetches and stores a single chunk of data."""
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")
    print(f"Fetching chunk for {symbol} ({resolution}) from {start_date_str} to {end_date_str}...")
    try:
        data = {
            "symbol": symbol, "resolution": resolution, "date_format": "1",
            "range_from": start_date_str, "range_to": end_date_str, "cont_flag": "1"
        }
        response = fyers.history(data=data)

        if response.get("code") == 200 and response.get("candles"):
            candles = response["candles"]
            print(f"  - Fetched {len(candles)} candles.")
            data_to_insert = [(datetime.datetime.fromtimestamp(c[0]), symbol, c[1], c[2], c[3], c[4], c[5], resolution) for c in candles]
            cursor.executemany(f"INSERT OR IGNORE INTO {HISTORICAL_TABLE} (timestamp, symbol, open, high, low, close, volume, resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", data_to_insert)
            return cursor.rowcount
        else:
            print(f"  - Could not fetch data for chunk. Response: {response.get('message', 'No message')}")
            return 0
    except Exception as e:
        print(f"  - An error occurred during chunk fetch/store: {e}")
        return 0

def fetch_and_store_historical_data(fyers: fyersModel.FyersModel, symbols: list, resolutions: list):
    """
    Fetches historical data for a list of symbols across multiple resolutions
    and stores it in a SQLite database.
    
    Args:
        fyers (fyersModel.FyersModel): An authenticated fyersModel instance.
        symbols (list): A list of stock symbols (e.g., ["NSE:SBIN-EQ"])
        resolutions (list): A list of data resolutions (e.g., ["D", "60", "15", "5", "1"])
    """
    # The db_setup.py script is now responsible for all table creation.
    # We will connect and disconnect for each symbol to minimize db lock time.

    # Fetch data up to yesterday to ensure we only get complete daily candles.
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
            # Check for the latest existing data point for this symbol and resolution
            cursor.execute(f"""
                SELECT MAX(timestamp) FROM {HISTORICAL_TABLE}
                WHERE symbol = ? AND resolution = ?
            """, (symbol, resolution))
            # The query now correctly filters by both symbol AND resolution.
            latest_timestamp_str = cursor.fetchone()[0]
            
            # If data exists, start fetching from the day after the last known date to avoid re-fetching the last day.
            # If no data exists, we'll use the default start date defined below.
            start_date_offset = datetime.timedelta(days=1) if latest_timestamp_str else datetime.timedelta(days=0)
            
            if latest_timestamp_str:
                # If data exists, start fetching from the last known date
                overall_start_date = datetime.datetime.strptime(latest_timestamp_str, '%Y-%m-%d %H:%M:%S').date() + start_date_offset
                print(f"Existing data found for {symbol} ({resolution}). Last entry: {overall_start_date}. Fetching new data since then.")
            else:
                # If no data exists, fetch the full default range from config
                if resolution == "D":
                    overall_start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_DAILY, "%Y-%m-%d").date()
                else:
                    overall_start_date = datetime.datetime.strptime(config.DEFAULT_START_DATE_INTRADAY, "%Y-%m-%d").date()
                print(f"No existing data for {symbol} ({resolution}). Fetching full range.")

            # --- Chunking Logic ---            
            overall_end_date = datetime.date.today()
            max_days_per_call = _get_max_days_for_resolution(resolution)

            for start_chunk, end_chunk in _get_date_chunks(overall_start_date, overall_end_date, max_days_per_call):
                rows_stored = _fetch_and_store_chunk(fyers, symbol, resolution, start_chunk, end_chunk, cursor)
                if rows_stored > 0:
                    print(f"  - Stored {rows_stored} new candles.")
                    con.commit() # Commit after each successful chunk
                else:
                    print(f"  - No new data for chunk or an error occurred.")

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
                    with sqlite3.connect(config.HISTORICAL_MARKET_DB_FILE) as con:
                        cursor = con.cursor()
                        _fetch_and_store_chunk(fyers, option_symbol, "1", current_date, current_date, cursor)
                        con.commit()
                        
            except Exception as e:
                print(f"  - Error processing {index_name} for {current_date}: {e}")

        current_date += datetime.timedelta(days=1)


def get_atm_option_symbols(fyers: fyersModel.FyersModel):
    """
    Calculates ATM option symbols for NIFTY, BANKNIFTY, SENSEX, and BANKEX.

    Args:
        fyers (fyersModel.FyersModel): An authenticated fyersModel instance.

    Returns:
        list: A list of ATM option symbols formatted for Fyers API.
    """
    indices = {
        "NIFTY": {"symbol": "NSE:NIFTY50-INDEX", "strike_interval": 100, "name": "NIFTY", "exchange": "NSE", "month_format": "%b"},
        "BANKNIFTY": {"symbol": "NSE:NIFTYBANK-INDEX", "strike_interval": 100, "name": "BANKNIFTY", "exchange": "NSE", "month_format": "%b"},
        # Per Fyers documentation, BSE options also use the short month name format.
        "SENSEX": {"symbol": "BSE:SENSEX-INDEX", "strike_interval": 100, "name": "SENSEX", "exchange": "BSE", "month_format": "%b"},
        "BANKEX": {"symbol": "BSE:BANKEX-INDEX", "strike_interval": 100, "name": "BANKEX", "exchange": "BSE", "month_format": "%b"},
    }

    option_symbols = []

    for index_name, index_data in indices.items():
        try:
            # Get the LTP for the index
            ltp_data = fyers.quotes({"symbols": index_data["symbol"]})
            if ltp_data["code"] == 200 and ltp_data["d"]:
                ltp = ltp_data["d"][0]["v"]["lp"]
                print(f"LTP for {index_name}: {ltp}")

                # Calculate the ATM strike
                strike_interval = index_data["strike_interval"]
                atm_strike = round(ltp / strike_interval) * strike_interval
                print(f"ATM Strike for {index_name}: {atm_strike}")

                # Get expiry dates
                option_chain_data = fyers.optionchain({"symbol": index_data["symbol"], "strikecount": 1})
                if option_chain_data["code"] == 200 and option_chain_data["data"]["expiryData"]:
                    expiry_dates = [e['expiry'] for e in option_chain_data["data"]["expiryData"]]
                    nearest_expiry_timestamp = int(expiry_dates[0])
                    expiry_date = datetime.datetime.fromtimestamp(nearest_expiry_timestamp)

                    # Construct the option symbols based on the exchange
                    year = str(expiry_date.year)[-2:]
                    month_format = index_data["month_format"]
                    day = expiry_date.strftime("%d") # e.g., '05', '11'
                    
                    month = expiry_date.strftime(month_format).upper()
                    ce_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}CE"
                    pe_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}PE"

                    option_symbols.extend([ce_symbol, pe_symbol])
                    print(f"Constructed symbols: {ce_symbol}, {pe_symbol}")

                else:
                    print(f"Could not fetch expiry dates for {index_name}: {option_chain_data}")

            else:
                print(f"Could not fetch LTP for {index_name}: {ltp_data}")

        except Exception as e:
            print(f"Error processing index {index_name}: {e}")

    return option_symbols


if __name__ == "__main__":
    try:
        print("-------------------- Starting Historical Data Fetch --------------------")
        
        # 1. Initialize the Fyers model
        access_token = get_access_token()
        fyers = get_fyers_model(access_token)

        # 2. Get the list of symbols to fetch
        # Fetch the full Nifty 50 for more comprehensive backtesting options
        symbols_to_fetch = get_top_nifty_stocks(top_n=50)
        print(f"\nFetching data for the following symbols: {symbols_to_fetch}")

        # 3. Define the resolutions to fetch
        resolutions_to_fetch = ["D", "60", "30", "15", "5", "1"]

        # 4. Fetch and store the data for all resolutions
        fetch_and_store_historical_data(
            fyers=fyers,
            symbols=symbols_to_fetch,
            resolutions=resolutions_to_fetch
        )

        # 5. Fetch historical data for ATM options for the last 100 days
        # This will populate the database for the live engine's warm-up process.
        print("\n-------------------- Starting Historical Options Data Fetch --------------------")
        end_date_options = datetime.date.today()
        start_date_options = end_date_options - datetime.timedelta(days=100)
        fetch_historical_options_data(fyers, start_date_options, end_date_options)
        print("-------------------- Historical Options Data Fetch Complete --------------------")

        print("-------------------- Historical Data Fetch Complete --------------------")

    except Exception as e:
        print(f"An error occurred in the main execution block: {e}")
        print("Please ensure your '.env' file is set up and you have a valid 'fyers_tokens.json'.")
        print("You can generate tokens by running 'python src/auth.py' manually.")
