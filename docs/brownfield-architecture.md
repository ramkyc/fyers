# Brownfield Architecture: Fyers Trading Platform

*This document reflects the state of the codebase as of the implementation of live configuration management and separated trade logs.*

## 1. Project Overview

This project is a trading platform that interfaces with the Fyers API. It provides a comprehensive suite of tools for backtesting trading strategies against historical data and simulating live paper trading. The primary user interface is a web-based dashboard built with Streamlit, which allows users to configure and run backtests, manage live trading settings, and view performance reports.

The system is designed with a clear separation of concerns, isolating data fetching, strategy logic, backtesting, live trading, and user interface into distinct components.

## 2. Core Components

### `src/auth`
- **Purpose**: Manages the entire Fyers API authentication flow.
- **Key Files**: `auth.py`
- **Functionality**: Handles the OAuth2 process, including generating auth codes, creating access/refresh tokens, and storing them in `fyers_tokens.json`. Provides helper functions to get an authenticated `fyersModel` instance.

### `src/data` & `src/fetch_historical_data.py`
- **Purpose**: Responsible for populating and managing the historical market database.
- **Key Files**: `fetch_historical_data.py`, `fetch_symbol_master.py`, `archive_live_data.py`, `check_data_coverage.py`
- **Functionality**:
    - `fetch_historical_data.py`: Intelligently fetches historical candle data for multiple resolutions. It handles API rate limits by breaking large date ranges into smaller, valid chunks. On subsequent runs, it only downloads data that is missing, making it highly efficient.
    - `fetch_symbol_master.py`: Downloads the complete Fyers symbol master files (for Equity and F&O), processes them, and stores critical information like `lot_size` into the `symbol_master` table.
    - `archive_live_data.py`: A daily maintenance script that moves captured live tick data from the temporary live database to the permanent historical database.
    - `check_data_coverage.py`: A utility script to connect to the historical database and print a detailed summary of the data coverage for each symbol and resolution.

### `src/tick_collector.py`
- **Purpose**: A class-based scheduler (`TradingScheduler`) that manages the lifecycle of the live trading engine.
- **Functionality**: It reads its configuration from `live_config.yaml`, starts the `LiveTradingEngine` before market open, stops it after market close, and triggers the `archive_live_data.py` script to clean up daily data. It also manages its own process via a PID file (`live_engine.pid`).

### `src/paper_trading`
- **Purpose**: Contains the core logic for managing a trading account's state.
- **Key Files**: `portfolio.py`, `oms.py` (Order Management System), `engine.py` (Live Trading Engine)
- **Functionality**:
    - `Portfolio`: Tracks cash, positions, and P&L for a trading session.
    - `OrderManager`: Simulates or places real orders, updating the portfolio accordingly.
    - `LiveTradingEngine`: Inherits from the Fyers `FyersDataSocket` class. It acts as the primary event handler for all WebSocket communications, processes live ticks, resamples them into 1-minute bars, and feeds them to the active strategy.

### `src/backtesting`
- **Purpose**: Provides a flexible, event-driven backtesting engine.
- **Key Files**: `engine.py`
- **Functionality**: The `BacktestingEngine` simulates the passage of time by iterating through historical data candle-by-candle. It supports both 'Positional' and 'Intraday' trading modes, with rules for time-windowed entries and automated end-of-day position closing. This event-driven model provides a more realistic simulation of live trading conditions.
- **Isolation**: Each backtest run uses a dedicated, in-memory `BacktestPortfolio` and is assigned a unique `run_id` to ensure complete isolation of its trade logs. The `BacktestPortfolio` is defined in `src/backtesting/portfolio.py`.

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
- **Key Files**: `dashboard.py`, `backtesting_ui.py`, `papertrader_ui.py`, `utils.py`, `live_config_manager.py`
- **Functionality**: A modular Streamlit application.
    - `dashboard.py`: Acts as the main entry point and router, displaying the top-level menu.
    - `backtesting_ui.py`: Contains all UI components for the backtesting and optimization tab.
    - `papertrader_ui.py`: Contains UI components for the live paper trading monitor, including controls to configure the live engine and start/stop it.
    - `live_config_manager.py`: A crucial module that acts as the bridge between the UI and the live engine. It manages the `live_config.yaml` and `live_engine.pid` files, providing a safe interface to start, stop, and configure the background process.
    - `utils.py`: A collection of shared helper functions for loading data and connecting to databases, used by the other UI modules.

## 3. Data Architecture & Flow

The application uses three separate SQLite databases to maintain a clean separation of data.

- **`data/historical_market_data.sqlite`**:
  - **Purpose**: Stores all permanent historical market data.
  - **Tables**:
    - `historical_data`: Contains historical OHLCV candle data.
    - `historical_ticks`: Contains archived tick-by-tick data from live sessions.
    - `symbol_master`: Contains instrument details, including lot sizes, downloaded from Fyers.
  - **Populated By**: `src/fetch_historical_data.py`, `src/fetch_symbol_master.py`, and `src/archive_live_data.py`.
  - **Read By**: `src/backtesting/engine.py`, `src/paper_trading/engine.py`, and `web_ui/dashboard.py`.

- **`data/live_market_data.sqlite`**:
  - **Purpose**: A temporary database to store live tick data captured during a single trading session.
  - **Lifecycle**: This database is cleared out daily by the archiving script.
  - **Populated By**: `src/paper_trading/engine.py` (LiveTradingEngine)
  - **Read By**: `src/archive_live_data.py` and monitoring scripts.

- **`data/trading_log.sqlite`**:
  - **Purpose**: Stores the results of trading activity.
  - **Tables**:
    - `backtest_trades`: A log of all individual trades from backtesting runs, distinguished by a `run_id`.
    - `live_paper_trades`: A log of all individual trades from live paper trading sessions.
    - `bt_portfolio_log`: A time-series log of portfolio value for backtest runs.
    - `pt_portfolio_log`: A time-series log of portfolio value for live paper trading runs.
    - `live_positions`: Stores the state of currently open positions in the live paper trading engine.
    - `pt_live_debug_log`: A structured log for debugging messages from the live engine.
  - **Populated By**: `src/paper_trading/oms.py`, `src/paper_trading/portfolio.py`.
  - **Read By**: `web_ui/dashboard.py` to display logs and reports.

## 4. Configuration Management

- **`.env` file**: Stores all secrets and environment-specific variables (API keys, credentials, etc.). This file is NOT committed to version control.
- **`config.py`**: Loads variables from the `.env` file and exposes them to the application. It also defines key file paths, ensuring consistency across the project.
- **`data/live_config.yaml`**: A user-managed file that defines the strategy, symbols, and parameters for the live trading engine. It is written to by the Streamlit dashboard and read by `tick_collector.py` on startup. This file is added to `.gitignore`.

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
    python src/fetch_symbol_master.py
    ```bash
    python src/fetch_historical_data.py
    ```

4.  **Run the Dashboard**:
    ```bash
    streamlit run web_ui/dashboard.py 
    ```

5.  **Run Live Trading (Optional)**:
    - The live trading engine is now managed directly from the Streamlit dashboard.
    - Navigate to the "Live Paper Trading Monitor" tab, configure your strategy, and click "Start Live Engine".

## 6. Identified Technical Debt & Risks

- **Thread-Safe Database Access**: The `LiveTradingEngine` receives data on a background thread managed by the Fyers library. To prevent `database is locked` errors, the engine now creates a new, short-lived SQLite connection within the `on_message` handler for each write operation, ensuring thread safety.
- **Hardcoded Holidays**: The `src/market_calendar.py` file contains a hardcoded list of holidays for 2025. This will need to be updated annually or replaced with a dynamic holiday calendar API.
- **Live Order Execution**: The live order placement in `oms.py` assumes the order is filled at the signal price. A production-grade system would need to poll for the actual fill price and handle partial fills.
- **Indefinite Tick Growth**: The `historical_ticks` table will grow indefinitely. A future enhancement could involve partitioning this data by month or year into separate files or tables for better performance.
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
├── data/ # Ignored by git
│   ├── historical_market_data.sqlite
│   ├── live_config.yaml
│   ├── live_engine.pid
│   ├── live_market_data.sqlite
│   └── trading_log.sqlite
├── docs/
│   ├── brownfield-architecture.md
│   ├── architecture-live-config.md
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
│   ├── fetch_historical_data.py
│   ├── fetch_symbol_master.py
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
│   ├── tick_collector.py
│   └── trading_scheduler.py
├── tests/
│   ├── paper_trading/
│   └── strategies/
└── web_ui/
    ├── __init__.py
    ├── backtesting_ui.py
    ├── dashboard.py
    ├── live_config_manager.py
    ├── papertrader_ui.py
    └── utils.py
```