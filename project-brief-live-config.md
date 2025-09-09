# Project Brief: Live Trading Configuration via Dashboard

## 1. Project Overview

*   **Introduction:** This project aims to decouple the live trading configuration from the application's source code. Currently, the strategy, symbols, and parameters for the live paper trading session are hardcoded within the `tick_collector.py` script. This makes it inflexible and requires a code change and redeployment for any adjustments.
*   **Problem Statement:** The user cannot easily change the live trading strategy or its parameters without modifying the core application code, which is inefficient and risky.
*   **Proposed Solution:** We will create a system that allows the user to define the live trading configuration through the Streamlit dashboard. These settings will be saved to a dedicated configuration file, which the `tick_collector.py` process will read upon startup.

## 2. Business Objectives & Success Metrics

*   **Objective:** To significantly increase the flexibility and usability of the live paper trading system, enabling rapid experimentation with different strategies and parameters in a live environment without requiring code deployments.
*   **Success Metric (KPI):** A user can select a strategy, its symbols, and its parameters in the dashboard, save the configuration, and have the `tick_collector.py` process use these new settings the next time it starts.
*   **Success Metric (KPI):** The system remains stable, and the communication between the dashboard (front-end) and the live engine (back-end) is reliable and does not introduce race conditions.

## 3. Scope & Features

### 3.1. Dashboard UI Enhancements

*   A new set of controls will be added to the sidebar, visible only when the "Live Paper Trading Monitor" mode is active.
*   These controls will allow the user to select:
    1.  **Strategy:** A dropdown populated from the `STRATEGY_MAPPING` dictionary.
    2.  **Symbols:** A multi-select box for choosing the symbols to trade.
    3.  **Strategy Parameters:** Dynamic controls (e.g., sliders) for the selected strategy's parameters.
*   A "Save Live Configuration" button will be added to persist the settings.

### 3.2. Configuration Management

*   A new, dedicated configuration file will be created, for example, `data/live_config.yaml`. This file will store the settings saved from the dashboard.
*   This file **will be added to `.gitignore`** as it contains user-specific settings and should not be part of the core source code.
*   The dashboard will be responsible for writing to this file.

### 3.3. Live Engine (`tick_collector.py`) Modifications

*   The `TradingScheduler.start_trading_engine` method will be refactored.
*   Instead of hardcoding the strategy, symbols, and parameters, it will now read them from the `data/live_config.yaml` file at startup.
*   If the configuration file does not exist, the engine should log a clear warning and default to a safe, pre-defined configuration (e.g., no symbols, no strategy) to prevent crashes.

## 4. Out of Scope

*   **Real-time Updates:** The live engine will **not** change its configuration while it is running. Changes made in the dashboard will only take effect on the next scheduled or manual (re)start of the `tick_collector.py` process. This is a critical simplification to reduce risk and complexity.
*   **Process Management from UI:** The dashboard will not be able to start, stop, or restart the `tick_collector.py` process. This remains a server-level operational task to be managed via the command line (e.g., with `cron` or `systemd`).

## 5. Stakeholders

*   **Project Owner:** You (the user).
*   **Execution Team:** Specialist agents from the BMad method (Architect, Dev, QA).

## 6. Risks & Dependencies

*   **Risk (Concurrency):** The dashboard (a web process) and the `tick_collector` (a background process) might try to access the configuration file at the same time. The file writing/reading logic must be atomic to prevent corruption.
*   **Risk (Validation):** The dashboard must validate the user's input to prevent saving an invalid configuration (e.g., short window > long window) that could cause the live engine to behave unexpectedly.
*   **Dependency:** This feature depends on the stability of the recently fixed `LiveTradingEngine`.

---

*This document will be used by the Architect to design the technical solution.*