# Plan: Fyers Trading Platform

## Objectives

This project provides a comprehensive trading platform that interfaces with the Fyers API. Its primary goals are:

- **Backtesting**: To test trading strategies against historical data using a high-performance vectorized engine.
- **Live Paper Trading**: To simulate trading strategies in real-time using live market data from the Fyers WebSocket.
- **Strategy Development**: To provide a flexible framework for creating and plugging in new trading strategies.
- **Analysis & Visualization**: To offer a web-based dashboard (Streamlit) for running backtests, optimizing parameters, and reviewing performance.

## Steps

The standard workflow for setting up and using the application is as follows:

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

4.  **Run the Dashboard for Backtesting & Analysis**:
    ```bash
    streamlit run web_ui/dashboard.py
    ```

5.  **Run Live Trading (Optional)**:
    ```bash
    python src/tick_collector.py
    ```

## Data Architecture

To ensure a clear separation between different operational modes and to prevent data conflicts, the application uses three distinct SQLite database files located in the `/data` directory:

-   **`historical_market_data.sqlite`**: Stores historical market data fetched by the `src/fetch_historical_data.py` script. This database is used exclusively by the backtesting engine.
    - **Populated By**: `src/fetch_historical_data.py`
    - **Read By**: `src/backtesting/engine.py` and `web_ui/dashboard.py`.

-   **`live_market_data.sqlite`**: Stores live market data captured in real-time by the `src/tick_collector.py` process.
    - **Populated By**: `src/paper_trading/engine.py` (LiveTradingEngine)
    - **Read By**: Potentially future analysis scripts.

-   **`trading_log.sqlite`**: Stores the results of trading activity.
    - **`paper_trades` table**: Logs individual trades from both backtesting and live trading.
    - **`portfolio_log` table**: Logs portfolio value over time, but **only from the live trading engine**.
    - **Populated By**: `src/paper_trading/oms.py` (for trades) and `src/paper_trading/portfolio.py` (for portfolio logs).
    - **Read By**: `web_ui/dashboard.py` to display live logs.

This separation ensures that live trading, historical fetching, and backtesting operations do not interfere with each other.
