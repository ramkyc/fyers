# Brownfield Architecture: Fyers Trading Platform

*This document reflects the state of the codebase after the implementation of the event-driven backtesting engine.*

## 1. Project Overview

This project is a trading platform that interfaces with the Fyers API. It provides a comprehensive suite of tools for both backtesting trading strategies against historical data and simulating live paper trading. The primary user interface is a web-based dashboard built with Streamlit, which allows users to configure and run backtests, optimize strategy parameters, and view performance reports and logs.

The system is designed with a clear separation of concerns, isolating data fetching, strategy logic, backtesting, live trading, and user interface into distinct components.

## 2. Core Components

### `src/auth`
- **Purpose**: Manages the entire Fyers API authentication flow.
- **Key Files**: `auth.py`
- **Functionality**: Handles the OAuth2 process, including generating auth codes, creating access/refresh tokens, and storing them in `fyers_tokens.json`. Provides helper functions to get an authenticated `fyersModel` instance.

### `src/data` & `src/fetch_historical_data.py`
- **Purpose**: Responsible for populating the historical market database.
- **Key Files**: `fetch_historical_data.py`, `archive_live_data.py`
- **Functionality**:
    - `fetch_historical_data.py`: Intelligently fetches historical candle data for multiple resolutions. It handles API rate limits by breaking large date ranges into smaller, valid chunks. On subsequent runs, it only downloads data that is missing, making it highly efficient.
    - `archive_live_data.py`: A daily maintenance script that moves captured live tick data from the temporary live database to the permanent historical database.
    - `check_data_coverage.py`: A utility script to connect to the historical database and print a detailed summary of the data coverage for each symbol and resolution.

### `src/tick_collector.py`
- **Purpose**: A scheduler script that manages the lifecycle of the live trading engine.
- **Functionality**: Starts the `LiveTradingEngine` before market open, stops it after market close, and triggers the `archive_live_data.py` script to clean up daily data.

### `src/paper_trading`
- **Purpose**: Contains the core logic for managing a trading account's state.
- **Key Files**: `portfolio.py`, `oms.py` (Order Management System), `engine.py` (Live Trading Engine)
- **Functionality**:
    - `Portfolio`: Tracks cash, positions, and P&L for a trading session.
    - `OrderManager`: Simulates or places real orders, updating the portfolio accordingly.
    - `LiveTradingEngine`: Inherits directly from the Fyers `FyersDataSocket` class. It acts as the primary event handler for all WebSocket communications (connection, messages, errors, closure), processes live ticks, and stores them in the database.

### `src/backtesting`
- **Purpose**: Provides a flexible, event-driven backtesting engine.
- **Key Files**: `engine.py`, `portfolio.py`
- **Functionality**: The `BacktestingEngine` simulates the passage of time by iterating through historical data candle-by-candle. It supports both 'Positional' and 'Intraday' trading modes, with rules for time-windowed entries and automated end-of-day position closing. This event-driven model provides a more realistic simulation of live trading conditions.
- **Isolation**: Each backtest run uses a dedicated, in-memory `BacktestPortfolio` and is assigned a unique `run_id` to ensure complete isolation of its trade logs.

### `src/strategies`
- **Purpose**: Defines the logic for making trading decisions.
- **Key Files**: `base_strategy.py`, `simple_ma_crossover.py`
- **Functionality**: Implements trading strategies. Each strategy must inherit from `BaseStrategy`. The `on_data` method is now the primary entry point for both live trading and the event-driven backtester, ensuring logic is consistent across both environments.

### `src/reporting`
- **Purpose**: Analyzes and presents portfolio performance.
- **Key Files**: `performance_analyzer.py`
- **Functionality**: Calculates key metrics like P&L, Sharpe Ratio, Max Drawdown, and Win Rate from a completed backtest or live session.

### `web_ui`
- **Purpose**: The main user interface for the application.
- **Key Files**: `dashboard.py`
- **Functionality**: A Streamlit application that allows users to configure and run single backtests or multi-parameter optimizations. It visualizes results with interactive charts and tables and displays logs from the trading database.

## 3. Data Architecture & Flow

The application uses three separate SQLite databases to maintain a clean separation of data. A daily archiving process ensures that live data is managed efficiently.

- **`data/historical_market_data.sqlite`**:
  - **Purpose**: Stores all permanent historical market data.
  - **Tables**:
    - `historical_data`: Contains historical OHLCV candle data.
    - `historical_ticks`: Contains archived tick-by-tick data from live sessions.
  - **Populated By**: `src/fetch_historical_data.py` and `src/archive_live_data.py`.
  - **Read By**: `src/backtesting/engine.py` and `web_ui/dashboard.py`.

- **`data/live_market_data.sqlite`**:
  - **Purpose**: A temporary database to store live tick data captured during a single trading session.
  - **Lifecycle**: This database is cleared out daily by the archiving script.
  - **Populated By**: `src/paper_trading/engine.py` (LiveTradingEngine)
  - **Read By**: `src/archive_live_data.py` and monitoring scripts.

- **`data/trading_log.sqlite`**:
  - **Purpose**: Stores the results of trading activity.
  - **Tables**:
    - `paper_trades`: A log of all individual trades from both backtesting and live simulation, distinguished by a `run_id`.
    - `portfolio_log`: A time-series log of portfolio value, used for generating equity curves. **This is intended for live trading sessions but is currently not populated.** Backtests generate an in-memory equity curve that is displayed directly on the dashboard.
  - **Populated By**: `src/paper_trading/oms.py` (for both backtesting and live trading).
  - **Read By**: `web_ui/dashboard.py` to display trade logs from any run.

## 4. Configuration Management

- **`.env` file**: Stores all secrets and environment-specific variables (API keys, credentials, etc.). This file is NOT committed to version control.
- **`config.py`**: Loads variables from the `.env` file and exposes them to the application. It also defines key file paths, ensuring consistency across the project.

## 5. Key Entry Points & Usage

1.  **Initialize the Database Schema**:
    ```bash
    python src/db_setup.py
    ```

2.  **Generate API Tokens (One-time manual step)**:
    ```bash
    python src/auth.py
    ```
    *(Follow the on-screen instructions to log in via browser and paste the redirected URL).*

3.  **Fetch Historical Data**:
    ```bash
    python src/fetch_historical_data.py
    ```

4.  **Run the Dashboard**:
    ```bash
    streamlit run web_ui/dashboard.py
    ```

5.  **Run Live Trading (Optional)**:
    - This is now a scheduled, automated process. To run it, deploy the code to the production environment where it will be managed by a scheduler like `cron`.
    - The main entry point for this process is `src/tick_collector.py`.

## 6. Identified Technical Debt & Risks

- **Thread-Safe Database Access**: The `LiveTradingEngine` receives data on a background thread managed by the Fyers library. To prevent `database is locked` errors, the engine now creates a new, short-lived SQLite connection within the `on_message` handler for each write operation, ensuring thread safety.
- **Hardcoded Holidays**: The `src/market_calendar.py` file contains a hardcoded list of holidays for 2025. This will need to be updated annually or replaced with a dynamic holiday calendar API.
- **Live Order Execution**: The live order placement in `oms.py` assumes the order is filled at the signal price. A production-grade system would need to poll for the actual fill price and handle partial fills.
- **Indefinite Tick Growth**: The `historical_ticks` table will grow indefinitely. A future enhancement could involve partitioning this data by month or year into separate files or tables for better performance.
- **Disabled Live Strategy Execution**: The `LiveTradingEngine` has been refactored to be a reliable tick collector, but the logic to execute strategies on live data has been temporarily disabled. This requires a new architectural approach for resampling ticks into bars before feeding them to a strategy.
- **WebSocket Deadlock (Mitigated)**: A previous version of the code could hang on shutdown because the `unsubscribe()` call would block the main thread while waiting for a response from the background thread. This was resolved by calling `connect(is_async=True)`, which prevents the library from blocking the main thread.

## 7. Project Source Tree

```
fyers/
├── .bmad-core/
├── .claude/
├── .env
├── .gitignore
├── CHANGELOG.md
├── config.py
├── data/
│   ├── historical_market_data.sqlite
│   ├── live_market_data.sqlite
│   └── trading_log.sqlite
├── docs/
│   ├── brownfield-architecture.md
│   ├── environment-management.md
│   ├── brainstorming-session-results.md
│   ├── Plan.md
│   ├── project-brief-opening-price-crossover.md
│   ├── prd-opening-price-crossover.md
│   ├── qa/
│   ├── reporting/
│   └── todo/
├── fyers_tokens.json
├── logs/
├── poetry.lock
├── pyproject.toml
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── archive_live_data.py
│   ├── auth.py
│   ├── backtesting/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── portfolio.py
│   ├── check_data_coverage.py
│   ├── db_setup.py
│   ├── debug_live_engine.py
│   ├── fetch_historical_data.py
│   ├── market_calendar.py
│   ├── paper_trading/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── oms.py
│   │   └── portfolio.py
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── backtesting-enhancements.md
│   │   └── performance_analyzer.py
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base_strategy.py
│   │   ├── opening_price_crossover.py
│   │   └── simple_ma_crossover.py
│   └── tick_collector.py
├── tests/
│   ├── paper_trading/
│   └── strategies/
└── web_ui/
    └── dashboard.py
```