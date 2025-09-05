# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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