# Feature Requests & Ideas Backlog

This document serves as a central backlog for all new features, enhancements, and major ideas for the TraderBuddy platform. When we decide to work on a feature from this list, the first step will be to create a formal Project Brief for it.

---

## Planned Features (Not Started)

### 1. Advanced Capital Management Module

*   **Goal:** To move beyond fixed-quantity trades and implement a dynamic capital allocation system.
*   **Core Requirements:**
    *   The system should be able to fetch real-time funds and margin information from the Fyers API.
    *   Strategies should be able to define position sizes based on a percentage of available capital or a fixed risk amount.
    *   The `OrderManager` needs to be enhanced to support different product types (`CNC`, `INTRADAY`, `MARGIN`).
    *   The dashboard should display a summary of available funds.
*   **Status:** Awaiting Project Brief.

### 2. New Personal Strategy: [Your Strategy Name Here]

*   **Goal:** To implement and test a new, proprietary trading strategy.
*   **Core Requirements:**
    *   The exact logic (entry signals, exit signals, stop-loss, targets) needs to be defined.
    *   We need to determine if the strategy requires any new data points or indicators that are not currently available in the system.
    *   This will likely require creating a new strategy file in `src/strategies/` and integrating it into the platform.
*   **Status:** Awaiting Project Brief.
*   
---

## In-Progress Features

### 1. Paper Trading System V2
*   **Goal:** To evolve the paper trading module into a sophisticated, multi-asset, multi-timeframe research tool.
*   **Status (as of 2025-09-10 EOD):**
    *   **Completed:** All major architectural changes for V2 have been implemented, including multi-timeframe strategy execution, dynamic configuration file generation, and a redesigned UI. The unit test suite is passing.
    *   **Current Blocker:** The live trading engine is still not executing trades as expected. The log files indicate that the engine starts but with `Symbols=0`.
    *   **Root Cause Analysis:** The issue is a suspected race condition in `src/tick_collector.py`. The main process appears to be loading the configuration *before* the `prepare_live_data.py` subprocess has finished creating the necessary `pt_config_*.yaml` files.
    *   **Next Step:** When the market opens tomorrow, the immediate priority is to debug the startup sequence in `tick_collector.py` to ensure the data preparation script runs and completes **synchronously** before the engine attempts to load its configuration.
*   **Associated Brief:** `docs/project-brief-papertrading-v2.md`

---


## Completed Features

### 1. Stabilize Live Trading and Backtesting
*   **Goal:** To diagnose and fix issues preventing the live paper trading engine from executing trades and to resolve regressions in the backtesting engine.
*   **Outcome:** Implemented detailed logging to debug the live engine, fixed several data contract and UI state bugs, and stabilized the backtesting engine for all timeframes. The system is now in a reliable working state.
*   **Status:** Completed.