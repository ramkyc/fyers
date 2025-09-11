# Paper Trading User Guide

This guide explains how to use the "Live Paper Trading Monitor" tab on the dashboard to run and monitor simulated trading strategies in real-time.

## 1. Overview

The live paper trading system is designed to simulate how your strategies would perform in a live market. It uses a separate background process (`src/tick_collector.py`) that is controlled entirely from the dashboard UI.
The live paper trading system is designed to simulate how your strategies would perform in a live market. It uses a separate background process (`src/trading_scheduler.py`) that is controlled entirely from the dashboard UI.

## 2. Running a Live Paper Trading Session

1.  **Navigate to the Monitor**: Open the dashboard and select "Live Paper Trading Monitor" from the sidebar menu.

2.  **Configure Live Trading**: Use the sidebar to configure your session:
    *   **Trading Mode**: Choose `Intraday` (positions are auto-squared-off at 15:14) or `Positional` (positions are held overnight).
    *   **Strategy**: Select the strategy you want to run.
    *   **Symbols**: Select the specific stocks or options you want the strategy to trade. By default, this list includes the top 10 Nifty stocks and the day's ATM index options.
    *   **Parameters**: Adjust the strategy's parameters and the **Trade Value (INR)**, which sets the capital allocated for each new position.

3.  **Start the Engine**: Click the "Start Live Engine" button. This will launch the trading engine as a background process on the machine where the dashboard is running.

4.  **Monitor Performance**:
    *   **Live Open Positions**: A table on the main panel will show all currently open positions, updating in near-real-time with the latest Mark-to-Market (MTM) P&L.
    *   **Live Session Logs**: Use the dropdown at the bottom to select the current or any past live session. You can view a full performance summary and the detailed trade log for the selected session.

5.  **Stop the Engine**: Click "Stop Live Engine" to gracefully shut down the background process.

## 3. Monitoring on a Server (e.g., AWS EC2)

When you run the live engine on a remote server, you can monitor its health directly from the command line.

1.  **Check if the Process is Running**:
    Log in to your server via SSH and use this command to see if the script is an active process.
    ```sh
    ps aux | grep trading_scheduler.py
    ```

2.  **View the Live Log Files**:
    The script outputs status messages to a `nohup.out` file (if started with `nohup`). You can "tail" this file to see live updates, including tick processing messages and any errors.
    ```sh
    tail -f nohup.out
    ```

3.  **Query the Database Directly**:
    This is the most definitive way to confirm that trades are being executed.
    ```sh
    # Watch the last 10 live trades, refreshing every 5 seconds
    while true; do clear; sqlite3 data/trading_log.sqlite "SELECT * FROM paper_trades WHERE run_id LIKE 'live_%' ORDER BY timestamp DESC LIMIT 10;"; sleep 5; done
    ```