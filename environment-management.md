# Environment Management Guide

This document outlines the different environments used for this project and the conventions for each. The system is designed to operate in two primary environments: a local development environment and a remote production environment.

## 1. Local Development Environment (macOS)

- **Purpose**: This is the primary environment for all development, debugging, and testing activities. All new features, bug fixes, and refactoring should be done here.
- **Location**: Your local MacBook Pro.
- **Setup**:
    - **Python**: Uses the `fyers-env` virtual environment to manage dependencies.
    - **Configuration**: Relies on a local `.env` file in the project root. This file contains API credentials and settings specific to development and should **never** be committed to version control.
    - **Databases**: All SQLite database files (`historical_market_data.sqlite`, `live_market_data.sqlite`, `trading_log.sqlite`) are stored locally in the `/data` directory.
- **Execution**:
    - Scripts are run manually from the command line (e.g., `python src/fetch_historical_data.py`).
    - The dashboard is run locally for testing and analysis (`streamlit run web_ui/dashboard.py`).

## 2. Production Environment (AWS EC2)

- **Purpose**: This environment is for automated, live operations, such as continuous data collection and running the live paper trading simulation.
- **Location**: A remote AWS EC2 instance.
- **Setup**:
    - **Operating System**: Amazon Linux.
    - **Poetry Installation**: Poetry must be installed manually. The recommended command is `curl -sSL https://install.python-poetry.org | python3 -`.
    - **PATH Configuration**: To ensure the `poetry` command is always available, the `~/.bash_profile` file must be updated with the following line:
      ```bash
      export PATH="$HOME/.local/bin:$PATH"
      ```
    - **Configuration**: Uses a separate `.env` file located on the EC2 instance itself. This file contains production-level credentials and settings.
    - **Databases**: While it can use local SQLite files on the instance, a production setup might be configured to use a more robust database service like Amazon RDS in the future.
- **Execution**:
    - **Activation**: After logging in and navigating to the project directory, the virtual environment must be activated for the session using `poetry shell`.
    - **Automated Scripts**: The `src/tick_collector.py` script is the primary process that runs during market hours. It should be started as a persistent background process (e.g., using `nohup poetry run ... &`).
    - The Streamlit dashboard can be run on the server for monitoring the live engine, but its primary purpose for heavy analysis and backtesting is best suited for the local development environment.

## Key Differences & Workflow

### Standard Deployment Workflow (EC2)

After committing and pushing changes from your local machine, follow these steps on the EC2 instance to deploy the update:

1.  **Connect and Navigate**: SSH into the server and `cd` to the project directory.
2.  **Update Code**: Force sync the local repository with the remote `main` branch.
    ```bash
    git fetch origin
    git reset --hard origin/main
    ```
3.  **Sync Environment**: Activate the virtual environment (`poetry shell`) and install any new or updated dependencies. This is a safe and idempotent command.
    ```bash
    poetry install
    ```
4.  **Update Database Schema**: Run the database setup script. This is also safe and will only create tables if they don't exist.
    ```bash
    python src/db_setup.py
    ```
5.  **Restart the Live Engine**: Stop the old process and start the new one with the updated code.
    ```bash
    # Stop the old process
    kill $(cat data/live_engine.pid)
    sleep 5
    # Start the new one
    nohup python src/tick_collector.py &
    ```

| Feature             | Development (Local macOS)                               | Production (AWS EC2)                                  |
|---------------------|---------------------------------------------------------|-------------------------------------------------------|
| **Purpose**         | Code, test, debug, analyze                              | Automate, collect live data, run live simulation      |
| **Credentials**     | Local `.env` file                                       | Separate `.env` file on the server                    |
| **Execution**       | Manual (CLI commands)                                   | Automated (`cron`, `systemd`)                         |
| **Data**            | Local SQLite files for testing and backtesting          | Live data capture and potentially a production database |

The standard workflow is:
1.  **Develop** new features or fix bugs on your local machine.
2.  **Test** thoroughly in the local environment using the backtesting engine and local data.
3.  **Commit** the changes to version control (Git).
4.  **Deploy** the updated code to the EC2 instance.
5.  **Run** the automated processes in the production environment.
