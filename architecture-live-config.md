# Architecture: Live Trading Configuration & Process Management

## 1. Introduction

This document outlines the technical architecture for implementing the "Live Trading Configuration" feature as defined in `docs/project-brief-live-config.md`. The primary challenge is to create a safe and reliable communication channel between the Streamlit dashboard (a web process) and the `tick_collector.py` script (a background server process).

## 2. Architectural Approach

We will use a **file-based communication mechanism**. This approach is simple, robust, and well-suited for the current application structure. It avoids the complexity of setting up a dedicated API or message queue for communication.

The core components of this architecture are:

1.  **A Shared Configuration File (`live_config.yaml`):** A human-readable YAML file will act as the "single source of truth" for the live trading engine's configuration. The dashboard will write to this file, and the `tick_collector` will read from it.
2.  **A Process ID (PID) File (`live_engine.pid`):** A simple text file will be used to track the status of the `tick_collector` process. The presence of this file indicates the engine is running, and it will contain the process ID for sending signals.
3.  **A Centralized Management Module (`live_config_manager.py`):** A new Python module will be created to encapsulate all logic for reading/writing the config file and managing the PID file. This prevents logic duplication and ensures atomic operations.

## 3. Component Design

### 3.1. `live_config.yaml`

-   **Location:** `data/live_config.yaml`
-   **Format:** YAML for readability and ease of use.
-   **Content:**
    ```yaml
    strategy: "Simple MA Crossover"
    symbols:
      - "NSE:SBIN-EQ"
      - "NSE:RELIANCE-EQ"
    params:
      short_window: 9
      long_window: 21
      trade_quantity: 100
    ```
-   **Git Status:** This file will be added to `.gitignore`.

### 3.2. `live_engine.pid`

-   **Location:** `data/live_engine.pid`
-   **Content:** A single line containing the Process ID of the running `tick_collector.py` script.
-   **Lifecycle:**
    -   Created when `tick_collector.py` starts.
    -   Deleted when `tick_collector.py` stops gracefully or is stopped via the UI.
-   **Git Status:** This file will be added to `.gitignore`.

### 3.3. `src/live_config_manager.py` (New Module)

This new module will provide a safe interface for interacting with the shared files.

-   `save_config(config_data)`: Writes the given dictionary to `live_config.yaml`.
-   `load_config()`: Reads `live_config.yaml` and returns a dictionary. Handles file-not-found errors.
-   `get_engine_status()`: Checks for the existence and validity of `live_engine.pid` to determine if the engine is running.
-   `start_engine()`: Launches `tick_collector.py` as a background process using `subprocess.Popen` and creates the PID file.
-   `stop_engine()`: Reads the PID, sends a graceful `SIGTERM` signal, and cleans up the PID file.

### 3.4. `web_ui/dashboard.py` Modifications

-   The "Live Paper Trading Monitor" sidebar will be populated with controls (dropdowns, sliders) for strategy, symbols, and parameters.
-   The "Save Live Configuration" button will call `live_config_manager.save_config()`.
-   The UI will call `live_config_manager.get_engine_status()` to determine the engine's state.
-   Based on the status, it will display either a "Start Live Engine" or "Stop Live Engine" button. These buttons will call the corresponding functions in the `live_config_manager`.

### 3.5. `src/tick_collector.py` Modifications

-   The `TradingScheduler` class will be modified.
-   On startup, it will create `data/live_engine.pid` with its own process ID.
-   It will wrap its main loop in a `try...finally` block to ensure the PID file is deleted upon any exit (graceful or crash).
-   The `start_trading_engine` method will no longer have hardcoded settings. It will call `live_config_manager.load_config()` to get its configuration.

## 4. Risk Mitigation

-   **Concurrency:** The risk of file corruption is low because the dashboard writes the config file, and the `tick_collector` only reads it on startup. They are not writing to the same file simultaneously. The PID file is also managed in a way that avoids race conditions.
-   **Permissions:** The user running the Streamlit application must have the necessary OS-level permissions to execute the `python` command and send signals to other processes. This is an operational consideration for the server setup.
-   **Orphaned Processes:** The PID file mechanism provides a robust way to track the live engine. If the dashboard crashes, the PID file remains, and on the next dashboard load, it can re-establish the status of the running engine.

---
*This document will be used by the Developer to implement the feature.*