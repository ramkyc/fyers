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
            
            current_start_date = overall_start_date
            while current_start_date <= overall_end_date:
                current_end_date = current_start_date + datetime.timedelta(days=max_days_per_call - 1)
                if current_end_date > overall_end_date:
                    current_end_date = overall_end_date

                start_date_str = current_start_date.strftime("%Y-%m-%d")
                end_date_str = current_end_date.strftime("%Y-%m-%d")

                print(f"Fetching chunk for {symbol} ({resolution}) from {start_date_str} to {end_date_str}...")
                try:
                    data = {
                        "symbol": symbol,
                        "resolution": resolution,
                        "date_format": "1",
                        "range_from": start_date_str,
                        "range_to": end_date_str,
                        "cont_flag": "1"
                    }
                    response = fyers.history(data=data)

                    if response.get("code") == 200 and response.get("candles"):
                        candles = response["candles"]
                        print(f"  - Fetched {len(candles)} candles.")

                        data_to_insert = [
                            (datetime.datetime.fromtimestamp(c[0]), symbol, c[1], c[2], c[3], c[4], c[5], resolution)
                            for c in candles
                        ]
                        cursor.executemany(f"""
                            INSERT OR IGNORE INTO {HISTORICAL_TABLE} (timestamp, symbol, open, high, low, close, volume, resolution)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, data_to_insert)
                        con.commit() # Commit after each successful chunk
                        if cursor.rowcount > 0:
                            print(f"  - Stored {cursor.rowcount} new candles.")
                        else:
                            print(f"  - Skipped existing data for chunk.")
                    else:
                        print(f"  - Could not fetch data for chunk. Response: {response.get('message', 'No message')}")

                except Exception as e:
                    print(f"  - An error occurred during chunk fetch/store: {e}")

                # Move to the next chunk
                current_start_date = current_end_date + datetime.timedelta(days=1)

        # Close the connection after processing all resolutions for the current symbol
        if 'con' in locals() and con:
            con.close()
            print(f"Connection closed for symbol {symbol}.")


def _get_bse_month_code(month: int) -> str:
    """Converts a month number to the single-character BSE code."""
    if 1 <= month <= 9:
        return str(month)
    return {
        10: 'O',
        11: 'N',
        12: 'D'
    }.get(month, '')


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
        "SENSEX": {"symbol": "BSE:SENSEX-INDEX", "strike_interval": 100, "name": "SENSEX", "exchange": "BSE", "month_format": "bse_code"},
        "BANKEX": {"symbol": "BSE:BANKEX-INDEX", "strike_interval": 100, "name": "BANKEX", "exchange": "BSE", "month_format": "bse_code"},
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
                    day = expiry_date.strftime("%d")
                    
                    if month_format == "%b":
                        month = expiry_date.strftime("%b").upper()
                        ce_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}CE"
                        pe_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}PE"
                    elif month_format == "bse_code":
                        month_code = _get_bse_month_code(expiry_date.month)
                        ce_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month_code}{day}{atm_strike}CE"
                        pe_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month_code}{day}{atm_strike}PE"

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
        # For this example, we'll fetch the top 10 Nifty stocks
        symbols_to_fetch = get_top_nifty_stocks(top_n=10)
        print(f"\nFetching data for the following symbols: {symbols_to_fetch}")

        # 3. Define the resolutions to fetch
        resolutions_to_fetch = ["D", "60", "30", "15", "5", "1"]

        # 4. Fetch and store the data for all resolutions
        fetch_and_store_historical_data(
            fyers=fyers,
            symbols=symbols_to_fetch,
            resolutions=resolutions_to_fetch
        )

        print("-------------------- Historical Data Fetch Complete --------------------")

    except Exception as e:
        print(f"An error occurred in the main execution block: {e}")
        print("Please ensure your '.env' file is set up and you have a valid 'fyers_tokens.json'.")
        print("You can generate tokens by running 'python src/auth.py' manually.")
