# Environment Management Guide

This document outlines the different environments used for this project, the rationale behind them, and the conventions for each. The system is designed to operate in two primary environments: a local development environment and a remote production environment.

## 1. Local Development Environment (Your Mac/PC)

-   **Purpose**: This is the primary environment for all analysis, strategy development, and backtesting. All new features, bug fixes, and experimental refactoring should be done here.
-   **Rationale**:
    -   **Cost-Effectiveness**: Backtesting, especially parameter optimization, is CPU-intensive. Running these heavy, experimental computations on a local machine is free, whereas running them on a paid cloud server like EC2 can become expensive.
    -   **Rapid Iteration**: The development cycle of tweaking a strategy, running a backtest, and analyzing results is much faster and more efficient when done locally.
    -   **Interactive Analysis**: The Streamlit dashboard is a rich, interactive GUI designed for deep analysis, which is best suited for a local desktop environment.
-   **Execution**:
    -   Scripts are run manually from the command line (e.g., `python src/fetch_historical_data.py`).
    -   The dashboard is run locally for analysis (`streamlit run web_ui/dashboard.py`).

## 2. Production Environment (AWS EC2)

-   **Purpose**: This environment is exclusively for automated, live paper trading. Its sole job is to run the `tick_collector.py` scheduler reliably during market hours.
-   **Rationale**:
    -   **Resource Isolation**: The live trading engine's time-critical mission is to capture every market tick in real-time. Dedicating the EC2 instance to this single task prevents resource contention (CPU, memory, I/O) that could be caused by running heavy backtests, ensuring the live engine never lags or misses data.
    -   **Stability**: The production environment should be a stable, controlled environment that changes as infrequently as possible to minimize the risk of failure. Separating it from the experimental and unstable nature of development work is a critical best practice.
-   **Execution**:
    -   Scripts are run automatically using scheduling tools like `cron` or as persistent services using `systemd`.
    -   The `src/tick_collector.py` script is the primary process that runs during market hours.

## Key Differences & Workflow

| Feature         | Development (Local)                             | Production (EC2)                                      |
| --------------- | ----------------------------------------------- | ----------------------------------------------------- |
| **Purpose**     | Code, test, debug, analyze, backtest, optimize  | Automate, collect live data, run live simulation      |
| **Execution**   | Manual (CLI commands)                           | Automated (`cron`, `systemd`)                         |
| **Primary App** | `streamlit run web_ui/dashboard.py`             | `python src/tick_collector.py`                        |

The standard workflow is:
1.  **Develop & Analyze** new strategies on your local machine.
2.  **Test** thoroughly in the local environment using the backtesting engine.
3.  **Commit** the changes to version control (Git).
4.  **Deploy** the updated and validated code to the EC2 instance.
5.  **Run** the automated processes in the production environment.