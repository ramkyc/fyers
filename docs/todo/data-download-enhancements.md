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

## Part 3: Data Completeness Verification

To ensure the integrity of our backtesting and analysis, it's crucial to verify that the historical data has been downloaded completely. This section outlines the methodology for this verification.

### 3.1. Methodology

The verification process involves comparing the number of records present in the database against the theoretically expected number of records for a given period.

1.  **Calculate Trading Days**: Determine the total number of market working days within the specified date range. This can be done by iterating through each day and using the `is_market_working_day` function from `src/market_calendar.py`.

2.  **Calculate Expected Candles per Day**: The Indian market is open from 09:15 to 15:30, which is 375 minutes. The expected number of candles per day for each resolution is:
    *   **1-minute**: 375 candles
    *   **5-minute**: 75 candles (375 / 5)
    *   **15-minute**: 25 candles (375 / 15)
    *   **30-minute**: 13 candles (12 full 30-min candles + 1 partial 15-min candle)
    *   **60-minute**: 7 candles (6 full 60-min candles + 1 partial 15-min candle)
    *   **Daily**: 1 candle

3.  **Calculate Total Expected Records**: Multiply the number of trading days by the expected candles per day for each resolution.
    `Total Expected = (Trading Days) * (Candles per Day)`

4.  **Compare with Actuals**: Use the `src/check_data_coverage.py` script to get the actual record count from the database and compare it with the calculated expected count.

### 3.2. Example Calculation

We want to work with data from 1st April, 2024 to till date.  
For a period with **356 trading days** (from `2024-04-01` to `2025-09-05`):

| Resolution | Actual Records | Trading Days | Candles/Day | Expected Records | Completeness |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1 min** | 133,290 | 356 | 375 | 133,500 | 99.84% |
| **5 min** | 26,658 | 356 | 75 | 26,700 | 99.84% |
| **15 min** | 8,886 | 356 | 25 | 8,900 | 99.84% |
| **30 min** | 4,623 | 356 | 13 | 4,628 | 99.89% |
| **60 min** | 2,490 | 356 | 7 | 2,492 | 99.92% |

**Note**: A completeness of >99.5% is generally considered excellent, as minor discrepancies can occur due to market-specific events like brief trading halts.