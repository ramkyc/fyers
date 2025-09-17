# TraderBuddy: Fyers Trading Platform

TraderBuddy is a comprehensive platform that interfaces with the Fyers API for backtesting and live paper trading of algorithmic strategies.

## Key Features

-   **Event-Driven Backtesting**: Test strategies against historical data with a realistic, event-driven engine.
-   **Parameter Optimization**: Use the dashboard to run optimizations and find the best parameters for your strategy.
-   **Live Paper Trading**: Simulate strategies in real-time using live market data from the Fyers WebSocket.
-   **Strategy Framework**: A flexible framework for creating and plugging in new trading strategies.
-   **Analysis Dashboard**: A web-based dashboard (built with Streamlit) for running backtests, optimizing parameters, and reviewing performance.

## Quick Start

### 1. Prerequisites

-   Python 3.12+
-   [Poetry](https://python-poetry.org/) for dependency management
-   A Fyers Trading Account.

### 2. Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd fyers
    ```

2.  **Install dependencies using Poetry:**
    This command reads the `pyproject.toml` and `poetry.lock` files to create a dedicated virtual environment and install the exact versions of all required packages. This ensures your environment is perfectly consistent and reproducible.
    ```bash
    poetry install
    ```

3.  **Activate the virtual environment:**
    All subsequent commands should be run inside this shell.
    ```bash
    poetry shell
    ```

### 3. Configuration & Setup

1.  **Create `.env` file**: Create a file named `.env` in the project root and add your Fyers API credentials. Refer to `docs/user_guide.md` for the required variables.
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
    ENVIRONMENT="dev" # Use "dev" for local, "prod" for EC2
    ```

2.  **Initialize Databases**: Run the setup script to create the necessary SQLite database files.
    ```bash
    python src/db_setup.py
    ```

3.  **Generate API Tokens**: Run the authentication script to generate your `fyers_tokens.json` file. You will be prompted to open a URL, log in, and paste the redirected URL back into the terminal.
    ```bash
    python src/auth.py
    ```

### 4. Usage

1.  **Fetch Historical Data**: Download data for backtesting. The script will intelligently fetch only the data that is missing.
    ```bash
    python src/fetch_historical_data.py
    ```
2.  **Launch the Analysis Dashboard**: Start the Streamlit app to run backtests, optimize strategies, and review results.
    ```bash
    streamlit run web_ui/dashboard.py
    ```