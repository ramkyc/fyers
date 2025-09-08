# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
-   **Refactored `tick_collector.py`**: Converted the scheduler script from a procedural design with global variables to a more robust and maintainable class-based `TradingScheduler`.

## [0.5.0] - 2025-09-08

### Added
-   **Contextual Dashboard UI**: The main dashboard now features a contextual sidebar menu, showing relevant controls for either "Backtesting" or "Live Paper Trading Monitor" modes.
-   **Live Monitor Auto-Refresh**: The Live Monitor tab now automatically refreshes, providing a near real-time view of system health and data collection.
-   **Live Data Preparation**: A new daily script (`prepare_live_data.py`) and scheduler job now pre-populates the necessary bar history for strategies, ensuring the live engine starts "hot".
-   **Live Trading Safety Switch**: Added a global `ENABLE_LIVE_TRADING` flag in `config.py` to prevent accidental placement of real orders. The system defaults to simulated paper trading.

### Fixed
-   **Live Data Engine**: Resolved a critical bug preventing the live engine from processing and storing ticks. The engine now reliably collects data, resamples it into 1-minute bars, and feeds it to the strategy.
-   **Strategy Execution**: Fixed an issue where live strategies were not receiving the required historical data to generate signals. The engine now provides a rolling window of bar history.
-   **BSE Option Symbols**: Corrected the symbol generation logic for SENSEX and BANKEX options to align with Fyers API documentation, resolving all subscription errors.

## [0.4.0] - 2025-09-05

### Added
-   **Event-Driven Backtesting Engine**: The backtesting engine has been completely refactored from a vectorized to an event-driven model. This provides a more realistic simulation and allows for complex time-based rules.
-   **Positional & Intraday Modes**: The dashboard and engine now support two backtest types. 'Positional' holds trades overnight, while 'Intraday' automatically closes all positions at the end of the day.
-   **Time-Windowed Entries**: Users can now specify exact start and end times in the UI, and the backtester will only consider entry signals within that time window each day.
-   **Isolated Backtest Runs**: Each backtest is now assigned a unique `run_id`, and a dedicated `BacktestPortfolio` class is used to ensure that all simulations and their logs are completely isolated from each other and from live trading.

### Changed
-   **Strategy Logic**: Strategies now use the `on_data` method for both backtesting and live trading, simplifying logic and ensuring consistency. The `generate_signals` method has been removed.
-   **Dashboard UI**: Upgraded date selectors to full datetime pickers and added a toggle for backtest type.
-   **Dynamic Intraday Exits**: The intraday exit time is no longer hardcoded and is now calculated dynamically based on the official market close time.

## [0.3.0] - 2025-09-05

### Added
-   **Data Coverage Verification**: Added a new script `src/check_data_coverage.py` to generate a detailed report on the completeness of the historical data in the database.
-   **Data Verification Documentation**: Documented the methodology for calculating and verifying data completeness in `docs/todo/data-download-enhancements.md`.

### Changed
-   **Robust Data Fetching**: Completely overhauled the data fetching logic in `src/fetch_historical_data.py` to use smaller, resolution-aware chunks, making it resilient to Fyers API rate limits and date range restrictions.
-   **Database Concurrency**: Improved database connection handling to open/close connections per symbol, significantly reducing the occurrence of `database is locked` errors.

### Fixed
-   **Missing Historical Data**: Fixed a critical bug that prevented hourly ('60') and daily ('D') data from being downloaded on subsequent runs.
-   **Invalid Symbol Formatting**: Corrected symbol formatting for stocks with special characters (e.g., `M&M`) and for those that already include hyphens in their names (e.g., `ITC`).
-   **BSE Option Symbol Generation**: Fixed the logic for constructing BSE index option symbols to use the correct single-character month codes.

## [0.2.0] - 2024-05-23

### Added
-   **Live Tick Data Archiving**: Implemented a new script `src/archive_live_data.py` to move daily live ticks from the `live_market_data.sqlite` database to a permanent `historical_ticks` table in `historical_market_data.sqlite`.
-   **Automated Archiving Schedule**: The `src/tick_collector.py` now schedules the archiving script to run automatically at 16:00 daily.
-   **Changelog**: Added this `CHANGELOG.md` to track project changes.

### Changed
-   **Intelligent Historical Data Fetching**: The `src/fetch_historical_data.py` script is now significantly more efficient. It checks for the latest existing data for each symbol and only downloads new data from that point forward, avoiding redundant API calls.
-   **Non-Destructive Historical Fetching**: The `fetch_historical_data.py` script no longer drops the `historical_data` table on each run. It now uses `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE` to safely append new data.