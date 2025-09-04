import json
import requests
from fyers_apiv3 import fyersModel
import datetime
import duckdb
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dateutil.relativedelta import relativedelta

from auth import get_fyers_model, get_access_token
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
        top_stocks = [f"NSE:{stock['symbol']}-EQ" for stock in sorted_stocks[:top_n]]

        return top_stocks

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return []

def fetch_and_store_historical_data(fyers: fyersModel.FyersModel, symbols: list, resolutions: list):
    """
    Fetches historical data for a list of symbols across multiple resolutions
    and stores it in a DuckDB database.

    Args:
        fyers (fyersModel.FyersModel): An authenticated fyersModel instance.
        symbols (list): A list of stock symbols (e.g., ["NSE:SBIN-EQ"])
        resolutions (list): A list of data resolutions (e.g., ["D", "60", "15", "5", "1"])
    """
    print(f"Connecting to database at: {config.MARKET_DB_FILE}")
    con = duckdb.connect(database=config.MARKET_DB_FILE, read_only=False)

    # Drop the table if it exists to ensure a clean schema
    con.execute(f"DROP TABLE IF EXISTS {HISTORICAL_TABLE};")

    # Create the table with the correct schema
    con.execute(f"""
        CREATE TABLE {HISTORICAL_TABLE} (
            timestamp TIMESTAMP,
            symbol VARCHAR,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            resolution VARCHAR,
            UNIQUE(timestamp, symbol, resolution)
        );
    """)
    print(f"Table '{HISTORICAL_TABLE}' is ready.")

    for resolution in resolutions:
        print(f"\n--- Fetching data for resolution: {resolution} ---")
        end_date = datetime.date.today()
        if resolution == "D":
            start_date = end_date - relativedelta(years=1) # 1 year for daily
        else:
            start_date = end_date - relativedelta(months=3) # 3 months for intraday
        
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        for symbol in symbols:
            print(f"Fetching historical data for {symbol} ({resolution}) from {start_date_str} to {end_date_str}...")
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
                    print(f"Successfully fetched {len(candles)} candles for {symbol} ({resolution}).")

                    # Prepare data for batch insertion
                    data_to_insert = []
                    for c in candles:
                        # Fyers API returns timestamp in epoch format
                        dt_object = datetime.datetime.fromtimestamp(c[0])
                        data_to_insert.append((dt_object, symbol, c[1], c[2], c[3], c[4], c[5], resolution))

                    # Use a prepared statement for efficient insertion
                    con.executemany(f"""
                        INSERT INTO {HISTORICAL_TABLE} (timestamp, symbol, open, high, low, close, volume, resolution)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (timestamp, symbol, resolution) DO NOTHING;
                    """, data_to_insert)
                    print(f"Successfully stored data for {symbol} ({resolution}).")
                else:
                    print(f"Could not fetch historical data for {symbol} ({resolution}). Response: {response.get('message', 'No message')}")

            except Exception as e:
                print(f"An error occurred while fetching/storing data for {symbol} ({resolution}): {e}")

    con.close()
    print("Database connection closed.")


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
        "SENSEX": {"symbol": "BSE:SENSEX-INDEX", "strike_interval": 100, "name": "SENSEX", "exchange": "BSE", "month_format": "%m"},
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
                    
                    if month_format == "%b":
                        month = expiry_date.strftime("%b").upper()
                        ce_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}CE"
                        pe_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{atm_strike}PE"
                    else:
                        month = str(expiry_date.month)
                        day = expiry_date.strftime("%d")
                        ce_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{day}{atm_strike}CE"
                        pe_symbol = f"{index_data['exchange']}:{index_data['name']}{year}{month}{day}{atm_strike}PE"

                    option_symbols.extend([ce_symbol, pe_symbol])

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
        resolutions_to_fetch = ["D", "60", "15", "5", "1"]

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
