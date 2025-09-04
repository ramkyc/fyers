# TODO: Data Download Enhancements

This document outlines the plan to implement a more sophisticated data download and management strategy for the Fyers Trading Platform.

## Part 1: Enhance Historical Options Data Fetching

The current method for fetching historical options data is too simplistic. It uses the current day's ATM strike for all historical data. The new approach will calculate the ATM strike for each historical day individually.

### 1.1. Create a Date-Iterating Fetcher

The main function in `src/fetch_historical_data.py` needs to be refactored to iterate through a given date range.

-   **Action**: Create a new primary function, e.g., `fetch_historical_options_data`.
-   **Logic**:
    -   It will accept a `start_date` and `end_date`.
    -   It will loop through each day in this range.
    -   Inside the loop, it will use `market_calendar.is_market_working_day()` to skip weekends and holidays.

### 1.2. Dynamic, Day-Specific ATM Strike Calculation

For each valid trading day in the loop, the script must determine the ATM strike for that specific day.

-   **Action**: Inside the daily loop, for each index (NIFTY, BANKNIFTY, etc.):
-   **Logic**:
    1.  Fetch the 1-minute candle data for the underlying index (e.g., `NSE:NIFTY50-INDEX`) for the 09:15 AM candle of that historical day.
    2.  Use the closing price of this candle to calculate the ATM strike price.

### 1.3. Historical Expiry and Symbol Construction

This is the most complex part. For each historical day, we need to construct the correct, tradable option symbol for the relevant expiry.

-   **Action**: Create two new helper functions.
-   **`get_historical_expiry(trade_date, index_name)`**:
    -   **Input**: The historical date being processed and the index name.
    -   **Logic**: Based on the index name, determine if it's a weekly or monthly expiry. Calculate the nearest future expiry date (e.g., the next Thursday for NIFTY weekly options) relative to the `trade_date`.
    -   **Output**: A `datetime.date` object for the correct expiry.
-   **`construct_option_symbol(index_data, strike, option_type, expiry_date)`**:
    -   **Input**: Index details, the calculated ATM strike, "CE" or "PE", and the calculated expiry date.
    -   **Logic**: Assemble the symbol string in the precise format required by the Fyers API (e.g., `NSE:NIFTY25JUL2412300CE`). This will require careful handling of year, month, and day formatting based on the exchange.

### 1.4. Fetch and Store Data

-   **Action**: With the dynamically generated option symbols for that day:
-   **Logic**:
    1.  Call the Fyers `history` API to fetch the data for these symbols for the single historical day.
    2.  Use `INSERT OR IGNORE` to store the data in `historical_market_data.sqlite`, ensuring no duplicates are added.

## Part 2: Implement Live Tick Data Archiving

Live tick data should be moved from the `live_market_data.sqlite` database to a permanent historical tick table at the end of each day.

### 2.1. Correct Live Tick Storage Schema

The current schema in `src/paper_trading/engine.py` for storing live ticks is incorrect (it uses OHLC fields). This needs to be corrected first.

-   **Action**: Modify the `CREATE TABLE` statement in `LiveTradingEngine.__init__`.
-   **New Schema**: The table in `live_market_data.sqlite` should be simpler, e.g., `(timestamp, symbol, ltp, volume)`.
-   **Table Name**: Rename the table from `historical_data` to `live_ticks` to avoid confusion.

### 2.2. Create an Archiving Script

-   **Action**: Create a new script `src/archive_live_data.py`.
-   **Purpose**: This script will be run by a scheduler (e.g., `cron`) after market close.
-   **Logic**:
    1.  Connect to both `live_market_data.sqlite` and `historical_market_data.sqlite`.
    2.  In `historical_market_data.sqlite`, create a new table `historical_ticks` if it doesn't exist, with the same schema as the `live_ticks` table.
    3.  Read all data from the `live_ticks` table.
    4.  Insert this data into the `historical_ticks` table.
    5.  Clear the `live_ticks` table to prepare it for the next trading day.

### 2.3. Update the Scheduler

-   **Action**: Modify `src/tick_collector.py` or create a new master scheduler script.
-   **Logic**: Add a new scheduled job to run `python src/archive_live_data.py` at a time after market close, for example, at 16:00.