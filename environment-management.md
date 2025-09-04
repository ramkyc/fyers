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
    - **Operating System**: Typically a Linux distribution.
    - **Configuration**: Uses a separate `.env` file located on the EC2 instance itself. This file contains production-level credentials and settings.
    - **Databases**: While it can use local SQLite files on the instance, a production setup might be configured to use a more robust database service like Amazon RDS in the future.
- **Execution**:
    - Scripts are run automatically using scheduling tools like `cron` or as persistent services using `systemd`.
    - The `src/tick_collector.py` script is the primary process that runs during market hours to collect live data and execute the live trading engine.
    - The Streamlit dashboard is generally not run in the production environment, as its purpose is analysis, which is done locally.

## Key Differences & Workflow

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

