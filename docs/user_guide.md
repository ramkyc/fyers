# TraderBuddy User Guide

Welcome to the TraderBuddy application! This guide will walk you through setting up and using the platform for backtesting and live paper trading.

## 1. Introduction

TraderBuddy is a comprehensive trading platform that interfaces with the Fyers API. Its primary goals are:

-   **Backtesting**: Test trading strategies against historical data using a high-performance vectorized engine.
-   **Live Paper Trading**: Simulate trading strategies in real-time using live market data.
-   **Strategy Development**: Provide a flexible framework for creating and plugging in new trading strategies.
-   **Analysis & Visualization**: Offer a web-based dashboard (Streamlit) for running backtests, optimizing parameters, and reviewing performance.

### Architectural Note: Separation of Concerns

The Backtesting and Live Trading systems are designed to be completely independent. You can run backtests and analyze results on the dashboard at any time, regardless of whether the market is open or the live trading engine is running. The "Live Paper Trading Monitor" is simply a control panel and window into the separate, scheduled `tick_collector.py` process.

## 2. Prerequisites
## 2. Understanding the Environments

This application is designed to be used in two distinct environments:

-   **Local Development Environment (Your Mac/PC)**: This is where you will perform most of your analysis. You'll use your local machine to set up the project, download historical data, and run the Streamlit dashboard for backtesting and strategy optimization.

-   **Production Environment (A Server like AWS EC2)**: This is where the automated live paper trading runs. The `tick_collector.py` script is designed to be deployed on a server where it can run continuously during market hours without your direct intervention.

This guide will first walk you through setting up your **local environment**.

## 3. Prerequisites

Before you begin, ensure you have the following:

-   **Python 3.8+**: Installed on your system.
-   **Git**: For cloning the repository.
-   **A Fyers Trading Account**: You will need your API credentials.

## 4. Installation & Setup (Local Environment)

Follow these steps to get the application running on your local machine.

### Step 1: Clone the Repository

Open your terminal and clone the project from its source.

```bash
git clone <your-repository-url>
cd fyers
```

### Step 2: Create and Activate a Virtual Environment

It's highly recommended to use a virtual environment to manage project dependencies.

```bash
# Create the virtual environment
python3 -m venv fyers-env

# Activate it (on macOS/Linux)
source fyers-env/bin/activate
```

### Step 3: Install Dependencies

Install all the required Python packages.

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

The application uses a `.env` file to manage your secret credentials.

1.  Create a file named `.env` in the project's root directory.
2.  Copy the content below into the file and fill in your Fyers API details.

```env
# .env file template

# --- Fyers API Credentials ---
FYERS_APP_ID="YOUR_APP_ID"
FYERS_SECRET_KEY="YOUR_SECRET_KEY"
FYERS_REDIRECT_URI="http://localhost:3000"

# --- Fyers Login Credentials (for automated token generation) ---
FYERS_USERNAME="YOUR_FYERS_USERNAME"
FYERS_PASSWORD="YOUR_FYERS_PASSWORD"
FYERS_PIN="YOUR_4_DIGIT_PIN"
FYERS_TOTP_KEY="YOUR_TOTP_SECRET_KEY"

# --- Environment Setting ---
ENVIRONMENT="dev"
```

### Step 5: Initialize the Databases

Run the setup script to create the necessary SQLite database files and tables.

```bash
python src/db_setup.py
```

### Step 6: Generate API Tokens

Run the authentication script to generate your initial `fyers_tokens.json` file. This is a one-time manual step.

```bash
python src/auth.py
```

You will be prompted to open a URL in your browser, log in to Fyers, and then paste the redirected URL back into the terminal.

## 5. Core Workflows (Using Your Local Environment)

### Fetching Historical Data

Before you can backtest, you need to download historical market data.

```bash
python src/fetch_historical_data.py
```

This script intelligently fetches data for the top 10 NIFTY50 stocks. On subsequent runs, it will only download new data that is missing, making it very efficient.

### Running Backtests & Analysis

The main user interface is the Streamlit dashboard.

1.  **Launch the Dashboard**:
    ```bash
    streamlit run web_ui/dashboard.py
    ```
2.  **Configure a Backtest**: Use the sidebar to select symbols, a date range, a resolution, and a strategy with its parameters.
3.  **Run a Single Backtest**: Click "Run Backtest" to see a detailed performance report, equity curve, and trade log.
4.  **Run an Optimization**: Check the "Enable Parameter Optimization" box. This allows you to define a range for strategy parameters. The engine will run backtests for all combinations and display the results in a heatmap, helping you find the best-performing parameters.

### Understanding the Backtest Output

After running a backtest, you will see several logs. Here’s what they mean:

#### Immediate Backtest Results

This area appears right after you click "Run Backtest" and shows the results for that **single, specific run**.

-   **Trade Log (under Backtest Results tab):**
    -   **Purpose:** To give you an immediate, quick-glance list of all the simulated BUY and SELL orders that were executed during the backtest you just ran.
    -   **When to use it:** Use this to quickly verify if the strategy traded as you expected. This log is temporary and only exists in memory for the current results.

-   **Raw Backtest Log (under Backtest Results tab):**
    -   **Purpose:** This is the detailed, step-by-step "console output" from the backtesting engine. It shows every signal generated, every order placement, and any intraday exit messages.
    -   **When to use it:** This is your primary tool for **deep debugging**. If a trade didn't happen when you thought it should have, this log will tell you why.

#### Trading Activity Logs (Permanent Archive)

This is the main section at the bottom of the dashboard where you can review the **permanent, saved history of any past run**—whether it was a backtest or a live paper trading session.

-   **Portfolio Log:** This shows how your portfolio's value changed over time. It is only populated by **live paper trading sessions**, not by backtests.
-   **Trade Log:** This is the **permanent, database record** of every single trade from the run you select in the dropdown. Use this to audit and analyze trades from any past session.

### Deploying for Live Trading & Archiving (Production Environment)

The live trading component is designed to be an automated, scheduled process, typically run on a server (like an AWS EC2 instance).

-   **Entry Point**: `src/tick_collector.py`
-   **Functionality**:
    -   At 9:14 AM on market days, it starts the `LiveTradingEngine`.
    -   The engine connects to the Fyers WebSocket, subscribes to symbols, and feeds live ticks to the selected strategy.
    -   At 3:31 PM, it stops the engine.
    -   At 4:00 PM, it runs the `src/archive_live_data.py` script, which moves the day's captured ticks from the temporary `live_market_data.sqlite` to the permanent `historical_market_data.sqlite` and clears the live table for the next day.

#### Monitoring the Live System

Once the `tick_collector.py` script is running on your EC2 instance, you can monitor its activity in several ways:

1.  **Check if the Process is Running**:
    Log in to your EC2 instance via SSH and use this command to see if the script is an active process.
    ```sh
    ps aux | grep tick_collector.py
    ```

2.  **View the Live Log Files**:
    The script outputs status messages. If you are running it as a background service, you can "tail" the log file to see live updates.
    -   If using `nohup`: `tail -f nohup.out`
    -   If using `systemd`: `journalctl -u your-service-name.service -f`

3.  **Query the Database Directly (Most Definitive Check)**:
    This method confirms that data is actively being written to the live database.
    
    -   **See the latest 5 ticks**:
        ```sh
        sqlite3 data/live_market_data.sqlite "SELECT * FROM live_ticks ORDER BY timestamp DESC LIMIT 5;"
        ```
    
    -   **Watch the tick count grow in real-time**: This command re-runs every 2 seconds, showing you the total tick count and the timestamp of the latest tick. It's the best way to confirm the system is healthy.
        ```bash
        watch -n 2 'sqlite3 data/live_market_data.sqlite "SELECT COUNT(*), MAX(timestamp) FROM live_ticks;"'
        ```
    You should see the count increase and the timestamp update continuously during market hours.

## 6. For Developers: Adding a New Strategy

The platform is designed to be easily extensible. To add your own trading strategy:

1.  **Create a Strategy File**: Create a new Python file in `src/strategies/`, for example, `my_new_strategy.py`.
2.  **Inherit from `BaseStrategy`**: Your strategy class must inherit from `src/strategies/base_strategy.py`.
3.  **Implement Core Methods**:
    -   `generate_signals(self, data)`: This method is for **backtesting**. It should contain vectorized logic (using pandas) to generate buy/sell signals across the entire historical dataset at once.
    -   `on_data(self, timestamp, market_data_all_resolutions, **kwargs)`: This is the primary method for both **backtesting and live trading**. It is called for each new data point (a historical bar in a backtest, or a newly completed bar in a live session). The `is_live_trading` flag within `kwargs` allows you to add context-specific logic if needed.
4.  **Register in Dashboard**: Open `web_ui/dashboard.py` and add your new strategy class to the `STRATEGY_MAPPING` dictionary. This will make it available in the strategy dropdown in the UI.

```python
# In web_ui/dashboard.py

from src.strategies.my_new_strategy import MyNewStrategy

STRATEGY_MAPPING = {
    "Simple MA Crossover": SMACrossoverStrategy,
    "My Awesome New Strategy": MyNewStrategy, # Add your strategy here
}
```

## 6. Troubleshooting

-   **`ImportError: attempted relative import with no known parent package`**: This error occurs if you run a script from within the `src/` directory (e.g., `python src/some_script.py`). The scripts are designed to be run from the project root. The pathing logic added to the top of each script should handle this, but if you encounter it, ensure you are in the `/fyers` root directory when running commands.
-   **Authentication Errors**: If you see errors related to tokens, ensure your `.env` file is correctly filled out and that you have a valid, non-expired `fyers_tokens.json` file. If needed, delete the old `fyers_tokens.json` and re-run `python src/auth.py`.
-   **Data Not Found in Dashboard**: If the dashboard shows no symbols or data, make sure you have successfully run `python src/fetch_historical_data.py` first.