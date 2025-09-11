# Backtesting User Guide

This guide will walk you through setting up your local environment and using the TraderBuddy dashboard for backtesting and strategy analysis.

## 1. Prerequisites

Before you begin, ensure you have the following:

-   **Python 3.12+**: Installed on your system.
-   **Poetry**: For dependency management.
-   **A Fyers Trading Account**: You will need your API credentials.

## 2. Installation & Setup (Local Environment)

Follow these steps to get the application running on your local machine.

### Step 1: Clone the Repository

Open your terminal and clone the project from its source.

```bash
git clone <your-repository-url>
cd fyers
```

### Step 2: Install Dependencies

This command reads the `pyproject.toml` and `poetry.lock` files to create a dedicated virtual environment and install the exact versions of all required packages.

```bash
poetry install
```

### Step 3: Activate the Virtual Environment

Each time you open a new terminal tab to work on this project, you must first navigate to the project directory and then run `poetry shell` to activate the environment for that session.

```bash
poetry shell
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

## 3. Core Backtesting Workflow

### Fetching Historical Data

Before you can backtest, you need to download historical market data.

```bash
python src/fetch_historical_data.py
```

This script intelligently fetches data for the top 50 NIFTY50 stocks. On subsequent runs, it will only download new data that is missing, making it very efficient.

### Running Backtests & Analysis

The main user interface is the Streamlit dashboard.

1.  **Launch the Dashboard**:
    ```bash
    streamlit run web_ui/dashboard.py
    ```
2.  **Configure a Backtest**: Use the sidebar on the "Backtesting" tab to select symbols, a date range, a timeframe, and a strategy with its parameters.
3.  **Run a Single Backtest**: Click "Run Backtest" to see a detailed performance report, equity curve, and trade log.
4.  **Run an Optimization**: Check the "Enable Parameter Optimization" box. This allows you to define a range for strategy parameters. The engine will run backtests for all combinations and display the results in a heatmap, helping you find the best-performing parameters.