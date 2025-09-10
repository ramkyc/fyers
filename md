# TraderBuddy: Fyers Trading Platform

TraderBuddy is a comprehensive trading platform that interfaces with the Fyers API for backtesting and live paper trading of algorithmic strategies.

## Key Features

-   **Event-Driven Backtesting**: Test strategies against historical data with a realistic, event-driven engine.
-   **Live Paper Trading**: Simulate strategies in real-time using live market data from the Fyers WebSocket.
-   **Strategy Framework**: A flexible framework for creating and plugging in new trading strategies.
-   **Analysis Dashboard**: A web-based dashboard (built with Streamlit) for running backtests, optimizing parameters, and reviewing performance.

## Quick Start

### 1. Prerequisites

-   Python 3.12+
-   [Poetry](https://python-poetry.org/) for dependency management.
-   A Fyers Trading Account.

### 2. Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd fyers
    ```

2.  **Install dependencies using Poetry:**
    This will create a virtual environment and install all required packages from `pyproject.toml`.
    ```bash
    poetry install
    ```

3.  **Activate the virtual environment:**
    Each time you open a new terminal tab to work on this project, you must first navigate to the project directory and then run `poetry shell` to activate the environment for that session.
    ```bash
    poetry shell
    ```

### 3. Configuration & Setup

1.  **Create `.env` file**: Create a file named `.env` in the project root and add your Fyers API credentials. Refer to `docs/user_guide.md` for the required variables.

2.  **Initialize Databases**: Run the setup script to create the necessary SQLite database files.
    ```bash
    python src/db_setup.py
    ```

3.  **Generate API Tokens**: Run the authentication script once to generate your `fyers_tokens.json` file.
    ```bash
    python src/auth.py
    ```

### 4. Usage

1.  **Fetch Historical Data**:
    ```bash
    python src/fetch_historical_data.py
    ```
2.  **Launch the Dashboard**:
    ```bash
    streamlit run web_ui/dashboard.py
    ```